import fs from "fs";
import path from "path";

/** Resolve fixtures root: FIXTURES_ROOT env, else ../data/fixtures from api cwd. */
export function fixturesRoot(): string {
  const env = process.env.FIXTURES_ROOT;
  if (env && env.trim()) {
    return path.resolve(env.trim());
  }
  return path.resolve(process.cwd(), "../data/fixtures");
}

export function normalizedRoot(): string {
  const env = process.env.NORMALIZED_ROOT;
  if (env && env.trim()) {
    return path.resolve(env.trim());
  }
  return path.resolve(process.cwd(), "../data/normalized");
}

export function tracksRoot(): string {
  const env = process.env.TRACKS_ROOT;
  if (env && env.trim()) {
    return path.resolve(env.trim());
  }
  return path.resolve(process.cwd(), "../data/tracks");
}

export function sceneDir(sceneId: string): string {
  // Prefer fixtures (demo), then normalized mini scenes.
  const fixture = path.join(fixturesRoot(), sceneId);
  if (fs.existsSync(fixture)) {
    return fixture;
  }
  return path.join(normalizedRoot(), sceneId);
}

export function readJsonFile<T>(filePath: string): T {
  const text = fs.readFileSync(filePath, "utf8");
  return JSON.parse(text) as T;
}

export function loadJsonl(filePath: string): Record<string, unknown>[] {
  if (!fs.existsSync(filePath)) {
    return [];
  }
  const text = fs.readFileSync(filePath, "utf8");
  const rows: Record<string, unknown>[] = [];
  for (const line of text.split("\n")) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    rows.push(JSON.parse(trimmed) as Record<string, unknown>);
  }
  return rows;
}

/**
 * Resolve tracks JSONL for a scene.
 * Order: in-scene demo/tracks files, then TRACKS_ROOT/<scene>.jsonl.
 */
export function resolveTracksPath(dir: string, sceneId?: string): string | null {
  for (const name of ["tracks_demo.jsonl", "tracks.jsonl", "tracks_expected.jsonl"]) {
    const candidate = path.join(dir, name);
    if (fs.existsSync(candidate)) return candidate;
  }
  const id = sceneId || path.basename(dir);
  const external = path.join(tracksRoot(), `${id}.jsonl`);
  if (fs.existsSync(external)) return external;
  return null;
}
