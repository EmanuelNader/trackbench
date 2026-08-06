-- CreateSchema
CREATE SCHEMA IF NOT EXISTS "public";

-- CreateTable
CREATE TABLE "Scene" (
    "id" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "numFrames" INTEGER NOT NULL,
    "weather" TEXT,
    "timeOfDay" TEXT,

    CONSTRAINT "Scene_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "Run" (
    "id" TEXT NOT NULL,
    "commitSha" TEXT NOT NULL,
    "createdAt" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP,
    "configJson" JSONB NOT NULL,
    "runKey" TEXT NOT NULL,
    "notes" TEXT,

    CONSTRAINT "Run_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "RunMetric" (
    "id" TEXT NOT NULL,
    "runId" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "value" DOUBLE PRECISION NOT NULL,

    CONSTRAINT "RunMetric_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "SceneMetric" (
    "id" TEXT NOT NULL,
    "runId" TEXT NOT NULL,
    "sceneId" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "value" DOUBLE PRECISION NOT NULL,

    CONSTRAINT "SceneMetric_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "FailureEvent" (
    "id" TEXT NOT NULL,
    "runId" TEXT NOT NULL,
    "sceneId" TEXT NOT NULL,
    "frame" INTEGER NOT NULL,
    "t" DOUBLE PRECISION NOT NULL,
    "kind" TEXT NOT NULL,
    "trackId" INTEGER,
    "gtId" TEXT,
    "severity" DOUBLE PRECISION NOT NULL,
    "featuresJson" JSONB NOT NULL,
    "clusterId" TEXT,

    CONSTRAINT "FailureEvent_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "Cluster" (
    "id" TEXT NOT NULL,
    "runId" TEXT NOT NULL,
    "label" TEXT,
    "size" INTEGER NOT NULL,
    "centroidJson" JSONB NOT NULL,

    CONSTRAINT "Cluster_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "Tag" (
    "id" TEXT NOT NULL,
    "eventId" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "author" TEXT NOT NULL,

    CONSTRAINT "Tag_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE INDEX "Run_commitSha_idx" ON "Run"("commitSha");

-- CreateIndex
CREATE UNIQUE INDEX "Run_runKey_key" ON "Run"("runKey");

-- CreateIndex
CREATE UNIQUE INDEX "RunMetric_runId_name_key" ON "RunMetric"("runId", "name");

-- CreateIndex
CREATE UNIQUE INDEX "SceneMetric_runId_sceneId_name_key" ON "SceneMetric"("runId", "sceneId", "name");

-- CreateIndex
CREATE INDEX "FailureEvent_runId_kind_idx" ON "FailureEvent"("runId", "kind");

-- CreateIndex
CREATE INDEX "FailureEvent_clusterId_idx" ON "FailureEvent"("clusterId");

-- CreateIndex
CREATE INDEX "Cluster_runId_idx" ON "Cluster"("runId");

-- CreateIndex
CREATE UNIQUE INDEX "Tag_eventId_name_key" ON "Tag"("eventId", "name");

-- AddForeignKey
ALTER TABLE "RunMetric" ADD CONSTRAINT "RunMetric_runId_fkey" FOREIGN KEY ("runId") REFERENCES "Run"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "SceneMetric" ADD CONSTRAINT "SceneMetric_runId_fkey" FOREIGN KEY ("runId") REFERENCES "Run"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "SceneMetric" ADD CONSTRAINT "SceneMetric_sceneId_fkey" FOREIGN KEY ("sceneId") REFERENCES "Scene"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "FailureEvent" ADD CONSTRAINT "FailureEvent_runId_fkey" FOREIGN KEY ("runId") REFERENCES "Run"("id") ON DELETE CASCADE ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "FailureEvent" ADD CONSTRAINT "FailureEvent_sceneId_fkey" FOREIGN KEY ("sceneId") REFERENCES "Scene"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "FailureEvent" ADD CONSTRAINT "FailureEvent_clusterId_fkey" FOREIGN KEY ("clusterId") REFERENCES "Cluster"("id") ON DELETE SET NULL ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "Tag" ADD CONSTRAINT "Tag_eventId_fkey" FOREIGN KEY ("eventId") REFERENCES "FailureEvent"("id") ON DELETE CASCADE ON UPDATE CASCADE;
