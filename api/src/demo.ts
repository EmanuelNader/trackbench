import fs from "fs";
import path from "path";
import { Prisma, PrismaClient } from "@prisma/client";
import { fixturesRoot, readJsonFile, sceneDir } from "./paths";

export type DemoBundle = {
  version: number;
  scene: {
    id: string;
    name: string;
    numFrames: number;
    weather?: string | null;
    timeOfDay?: string | null;
    description?: string | null;
  };
  run: {
    runKey: string;
    commitSha: string;
    configJson: Record<string, unknown>;
    notes?: string | null;
  };
  metrics: Record<string, number>;
  sceneMetrics: Record<string, Record<string, number>>;
  failures: Array<{
    scene_id: string;
    frame: number;
    t: number;
    kind: string;
    track_id: number | null;
    gt_id: string | null;
    severity: number;
    features: Record<string, unknown>;
  }>;
  clusters: Array<{
    bucket: string;
    label: string;
    size: number;
    event_indices: number[];
    event_ids?: string[];
    summary: Record<string, unknown>;
  }>;
  tracksFile?: string;
  gtFile?: string;
};

export function loadDemoBundle(sceneId = "synthetic_scene_001"): DemoBundle {
  const bundlePath = path.join(sceneDir(sceneId), "demo_bundle.json");
  if (!fs.existsSync(bundlePath)) {
    throw new Error(
      `demo bundle not found at ${bundlePath}. Run: python -m eval.write_demo_run`,
    );
  }
  return readJsonFile<DemoBundle>(bundlePath);
}

export async function bootstrapDemo(prisma: PrismaClient): Promise<{
  runId: string;
  runKey: string;
  sceneId: string;
  nFailures: number;
  nClusters: number;
  fixturesRoot: string;
}> {
  const bundle = loadDemoBundle();
  const sceneId = bundle.scene.id;

  await prisma.scene.upsert({
    where: { id: sceneId },
    create: {
      id: sceneId,
      name: bundle.scene.name,
      numFrames: bundle.scene.numFrames,
      weather: bundle.scene.weather ?? null,
      timeOfDay: bundle.scene.timeOfDay ?? null,
    },
    update: {
      name: bundle.scene.name,
      numFrames: bundle.scene.numFrames,
      weather: bundle.scene.weather ?? null,
      timeOfDay: bundle.scene.timeOfDay ?? null,
    },
  });

  // Wipe prior demo run (cascade deletes metrics/events/clusters/tags).
  const existing = await prisma.run.findUnique({
    where: { runKey: bundle.run.runKey },
  });
  if (existing) {
    await prisma.run.delete({ where: { id: existing.id } });
  }

  const run = await prisma.run.create({
    data: {
      commitSha: bundle.run.commitSha,
      configJson: bundle.run.configJson as Prisma.InputJsonValue,
      runKey: bundle.run.runKey,
      notes: bundle.run.notes ?? null,
    },
  });

  const metricEntries = Object.entries(bundle.metrics);
  if (metricEntries.length > 0) {
    await prisma.runMetric.createMany({
      data: metricEntries.map(([name, value]) => ({
        runId: run.id,
        name,
        value: Number(value),
      })),
    });
  }

  const sceneMetricRows: Array<{
    runId: string;
    sceneId: string;
    name: string;
    value: number;
  }> = [];
  for (const [sid, metrics] of Object.entries(bundle.sceneMetrics || {})) {
    for (const [name, value] of Object.entries(metrics)) {
      sceneMetricRows.push({
        runId: run.id,
        sceneId: sid,
        name,
        value: Number(value),
      });
    }
  }
  if (sceneMetricRows.length > 0) {
    await prisma.sceneMetric.createMany({ data: sceneMetricRows });
  }

  // Create clusters first, then events with clusterId links.
  const clusterIdByIndex = new Map<number, string>();
  const createdClusters: Array<{ id: string; eventIndices: number[] }> = [];

  for (const cluster of bundle.clusters) {
    const row = await prisma.cluster.create({
      data: {
        runId: run.id,
        label: cluster.label,
        size: cluster.size,
        centroidJson: {
          bucket: cluster.bucket,
          ...cluster.summary,
        } as Prisma.InputJsonValue,
      },
    });
    createdClusters.push({ id: row.id, eventIndices: cluster.event_indices });
    for (const idx of cluster.event_indices) {
      clusterIdByIndex.set(idx, row.id);
    }
  }

  for (let i = 0; i < bundle.failures.length; i++) {
    const f = bundle.failures[i];
    await prisma.failureEvent.create({
      data: {
        runId: run.id,
        sceneId: f.scene_id || sceneId,
        frame: f.frame,
        t: f.t,
        kind: f.kind,
        trackId: f.track_id ?? null,
        gtId: f.gt_id ?? null,
        severity: f.severity,
        featuresJson: (f.features || {}) as Prisma.InputJsonValue,
        clusterId: clusterIdByIndex.get(i) ?? null,
      },
    });
  }

  return {
    runId: run.id,
    runKey: run.runKey,
    sceneId,
    nFailures: bundle.failures.length,
    nClusters: createdClusters.length,
    fixturesRoot: fixturesRoot(),
  };
}
