import cors from "cors";
import express from "express";
import path from "path";
import { PrismaClient } from "@prisma/client";
import { z } from "zod";
import { bootstrapDemo } from "./demo";
import {
  loadJsonl,
  resolveTracksPath,
  sceneDir,
} from "./paths";

const prisma = new PrismaClient();
const app = express();
const port = Number(process.env.PORT) || 3001;

const TAG_NAMES = [
  "occlusion",
  "known-issue",
  "needs-relabel",
  "wontfix",
] as const;

app.use(cors());
app.use(express.json());

function metricsMap(
  rows: Array<{ name: string; value: number }>,
): Record<string, number> {
  const out: Record<string, number> = {};
  for (const r of rows) out[r.name] = r.value;
  return out;
}

app.get("/health", (_req, res) => {
  res.json({ ok: true });
});

/** Load committed demo_bundle.json into Postgres (idempotent via runKey). */
app.get("/demo/bootstrap", async (_req, res) => {
  try {
    const result = await bootstrapDemo(prisma);
    res.json(result);
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    res.status(500).json({ error: message });
  }
});

app.post("/demo/load", async (_req, res) => {
  try {
    const result = await bootstrapDemo(prisma);
    res.json(result);
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    res.status(500).json({ error: message });
  }
});

app.get("/runs", async (_req, res) => {
  const runs = await prisma.run.findMany({
    orderBy: { createdAt: "desc" },
    include: {
      metrics: true,
      _count: { select: { failureEvents: true, sceneMetrics: true } },
    },
  });

  res.json(
    runs.map((run) => {
      const m = metricsMap(run.metrics);
      return {
        id: run.id,
        runKey: run.runKey,
        commitSha: run.commitSha,
        createdAt: run.createdAt,
        notes: run.notes,
        mota: m.mota ?? null,
        ids: m.ids ?? null,
        motp: m.motp ?? null,
        fp: m.fp ?? null,
        fn: m.fn ?? null,
        frag: m.frag ?? null,
        metrics: m,
        nFailures: run._count.failureEvents,
        nScenes: run._count.sceneMetrics,
      };
    }),
  );
});

app.get("/runs/:id", async (req, res) => {
  const run = await prisma.run.findUnique({
    where: { id: req.params.id },
    include: {
      metrics: true,
      sceneMetrics: { include: { scene: true } },
      _count: { select: { failureEvents: true, clusters: true } },
    },
  });
  if (!run) {
    res.status(404).json({ error: "run not found" });
    return;
  }

  const byScene = new Map<
    string,
    {
      sceneId: string;
      name: string;
      numFrames: number;
      weather: string | null;
      timeOfDay: string | null;
      metrics: Record<string, number>;
    }
  >();

  for (const sm of run.sceneMetrics) {
    let entry = byScene.get(sm.sceneId);
    if (!entry) {
      entry = {
        sceneId: sm.sceneId,
        name: sm.scene.name,
        numFrames: sm.scene.numFrames,
        weather: sm.scene.weather,
        timeOfDay: sm.scene.timeOfDay,
        metrics: {},
      };
      byScene.set(sm.sceneId, entry);
    }
    entry.metrics[sm.name] = sm.value;
  }

  res.json({
    id: run.id,
    runKey: run.runKey,
    commitSha: run.commitSha,
    createdAt: run.createdAt,
    configJson: run.configJson,
    notes: run.notes,
    metrics: metricsMap(run.metrics),
    scenes: Array.from(byScene.values()),
    nFailures: run._count.failureEvents,
    nClusters: run._count.clusters,
  });
});

app.get("/runs/:id/diff/:baselineId", async (_req, res) => {
  res.json({});
});

app.get("/runs/:id/clusters", async (req, res) => {
  const clusters = await prisma.cluster.findMany({
    where: { runId: req.params.id },
    orderBy: [{ size: "desc" }, { id: "asc" }],
  });
  res.json(
    clusters.map((c) => ({
      id: c.id,
      runId: c.runId,
      label: c.label,
      size: c.size,
      centroidJson: c.centroidJson,
    })),
  );
});

app.get("/clusters/:id/events", async (req, res) => {
  const limit = Math.min(
    200,
    Math.max(1, Number(req.query.limit) || 50),
  );
  const offset = Math.max(0, Number(req.query.offset) || 0);

  const cluster = await prisma.cluster.findUnique({
    where: { id: req.params.id },
  });
  if (!cluster) {
    res.status(404).json({ error: "cluster not found" });
    return;
  }

  const [total, events] = await Promise.all([
    prisma.failureEvent.count({ where: { clusterId: cluster.id } }),
    prisma.failureEvent.findMany({
      where: { clusterId: cluster.id },
      orderBy: [{ frame: "asc" }, { kind: "asc" }],
      skip: offset,
      take: limit,
      include: { tags: true, scene: true },
    }),
  ]);

  res.json({
    cluster: {
      id: cluster.id,
      runId: cluster.runId,
      label: cluster.label,
      size: cluster.size,
      centroidJson: cluster.centroidJson,
    },
    total,
    limit,
    offset,
    events: events.map((e) => ({
      id: e.id,
      runId: e.runId,
      sceneId: e.sceneId,
      sceneName: e.scene.name,
      frame: e.frame,
      t: e.t,
      kind: e.kind,
      trackId: e.trackId,
      gtId: e.gtId,
      severity: e.severity,
      features: e.featuresJson,
      tags: e.tags.map((t) => ({ id: t.id, name: t.name, author: t.author })),
    })),
  });
});

app.get("/scenes/:id/frames/:frame", async (req, res) => {
  const sceneId = req.params.id;
  const frame = Number(req.params.frame);
  if (!Number.isInteger(frame) || frame < 0) {
    res.status(400).json({ error: "frame must be a non-negative integer" });
    return;
  }

  const dir = sceneDir(sceneId);
  const gtPath = path.join(dir, "gt.jsonl");
  const tracksPath = resolveTracksPath(dir);
  if (!tracksPath) {
    res.status(404).json({
      error: `no tracks jsonl under ${dir}`,
    });
    return;
  }

  const gtRows = loadJsonl(gtPath);
  const trackRows = loadJsonl(tracksPath);
  const gtRow = gtRows.find((r) => Number(r.frame) === frame);
  const trRow = trackRows.find((r) => Number(r.frame) === frame);
  if (!gtRow && !trRow) {
    res.status(404).json({ error: `frame ${frame} not found for ${sceneId}` });
    return;
  }

  const t =
    gtRow && typeof gtRow.t === "number"
      ? gtRow.t
      : trRow && typeof trRow.t === "number"
        ? trRow.t
        : frame * 0.5;

  res.json({
    sceneId,
    frame,
    t,
    ego: { x: 0, y: 0, yaw: 0 },
    gt: Array.isArray(gtRow?.dets) ? gtRow!.dets : [],
    tracks: Array.isArray(trRow?.tracks) ? trRow!.tracks : [],
    sources: {
      gt: path.basename(gtPath),
      tracks: path.basename(tracksPath),
    },
  });
});

/** Optional helper: list failure events for a run (used by scene player ticks). */
app.get("/runs/:id/events", async (req, res) => {
  const sceneId =
    typeof req.query.sceneId === "string" ? req.query.sceneId : undefined;
  const events = await prisma.failureEvent.findMany({
    where: {
      runId: req.params.id,
      ...(sceneId ? { sceneId } : {}),
    },
    orderBy: [{ frame: "asc" }, { kind: "asc" }],
    include: { tags: true },
  });
  res.json(
    events.map((e) => ({
      id: e.id,
      runId: e.runId,
      sceneId: e.sceneId,
      frame: e.frame,
      t: e.t,
      kind: e.kind,
      trackId: e.trackId,
      gtId: e.gtId,
      severity: e.severity,
      features: e.featuresJson,
      clusterId: e.clusterId,
      tags: e.tags.map((t) => ({ id: t.id, name: t.name, author: t.author })),
    })),
  );
});

app.get("/events/:id", async (req, res) => {
  const e = await prisma.failureEvent.findUnique({
    where: { id: req.params.id },
    include: { tags: true, scene: true, cluster: true },
  });
  if (!e) {
    res.status(404).json({ error: "event not found" });
    return;
  }
  res.json({
    id: e.id,
    runId: e.runId,
    sceneId: e.sceneId,
    sceneName: e.scene.name,
    frame: e.frame,
    t: e.t,
    kind: e.kind,
    trackId: e.trackId,
    gtId: e.gtId,
    severity: e.severity,
    features: e.featuresJson,
    clusterId: e.clusterId,
    clusterLabel: e.cluster?.label ?? null,
    tags: e.tags.map((t) => ({ id: t.id, name: t.name, author: t.author })),
  });
});

app.post("/events/:id/tags", async (req, res) => {
  const bodySchema = z.object({
    name: z.enum(TAG_NAMES),
    author: z.string().min(1).max(64).default("triage"),
  });
  const parsed = bodySchema.safeParse(req.body);
  if (!parsed.success) {
    res.status(400).json({
      error: "invalid body",
      details: parsed.error.flatten(),
      allowed: TAG_NAMES,
    });
    return;
  }

  const event = await prisma.failureEvent.findUnique({
    where: { id: req.params.id },
  });
  if (!event) {
    res.status(404).json({ error: "event not found" });
    return;
  }

  const tag = await prisma.tag.upsert({
    where: {
      eventId_name: {
        eventId: event.id,
        name: parsed.data.name,
      },
    },
    create: {
      eventId: event.id,
      name: parsed.data.name,
      author: parsed.data.author,
    },
    update: {
      author: parsed.data.author,
    },
  });

  res.status(201).json(tag);
});

app.delete("/events/:id/tags/:name", async (req, res) => {
  const name = req.params.name;
  if (!(TAG_NAMES as readonly string[]).includes(name)) {
    res.status(400).json({ error: "unknown tag", allowed: TAG_NAMES });
    return;
  }

  try {
    await prisma.tag.delete({
      where: {
        eventId_name: {
          eventId: req.params.id,
          name,
        },
      },
    });
  } catch {
    // already absent — treat as success for idempotent UI toggles
  }
  res.status(204).send();
});

app.listen(port, () => {
  console.log(`trackbench-api listening on http://localhost:${port}`);
});

process.on("SIGINT", async () => {
  await prisma.$disconnect();
  process.exit(0);
});

process.on("SIGTERM", async () => {
  await prisma.$disconnect();
  process.exit(0);
});
