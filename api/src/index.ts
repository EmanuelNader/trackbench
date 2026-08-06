import cors from "cors";
import express from "express";
import { PrismaClient } from "@prisma/client";

const prisma = new PrismaClient();
const app = express();
const port = Number(process.env.PORT) || 3001;

app.use(cors());
app.use(express.json());

app.get("/health", (_req, res) => {
  res.json({ ok: true });
});

app.get("/runs", async (_req, res) => {
  res.json([]);
});

app.get("/runs/:id", async (_req, res) => {
  res.json({});
});

app.get("/runs/:id/diff/:baselineId", async (_req, res) => {
  res.json({});
});

app.get("/runs/:id/clusters", async (_req, res) => {
  res.json([]);
});

app.get("/clusters/:id/events", async (_req, res) => {
  res.json([]);
});

app.get("/scenes/:id/frames/:frame", async (_req, res) => {
  res.json({});
});

app.post("/events/:id/tags", async (_req, res) => {
  res.status(201).json({});
});

app.delete("/events/:id/tags/:name", async (_req, res) => {
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
