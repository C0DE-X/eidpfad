#!/usr/bin/env node
/* Generate deterministic offline German production voices with text2wav/eSpeak-NG. */

import fs from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const text2wav = require("text2wav");

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const manifestPath = path.join(root, "shared", "narrative", "voice_manifest.de-DE.json");
const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));

for (const [index, line] of manifest.lines.entries()) {
  const profile = manifest.profiles[line.speaker];
  if (!profile) throw new Error(`Missing voice profile ${line.speaker}`);
  const relative = line.asset.replace("res://", "client/");
  const output = path.join(root, relative);
  fs.mkdirSync(path.dirname(output), { recursive: true });
  const bytes = await text2wav(line.text, {
    voice: profile.voice,
    speed: profile.speed,
    pitch: profile.pitch,
    amplitude: 116,
    wordGap: 2,
    noFinalPause: false,
  });
  fs.writeFileSync(output, Buffer.from(bytes));
  const sampleRate = Buffer.from(bytes).readUInt32LE(24);
  const byteRate = Buffer.from(bytes).readUInt32LE(28);
  const dataSize = Buffer.from(bytes).readUInt32LE(40);
  line.duration_ms = Math.round((dataSize / byteRate) * 1000);
  line.sample_rate = sampleRate;
  if ((index + 1) % 25 === 0) process.stdout.write(`Generated ${index + 1}/${manifest.lines.length}\n`);
}

fs.writeFileSync(manifestPath, JSON.stringify(manifest, null, 2) + "\n", "utf8");
fs.writeFileSync(path.join(root, "client", "assets", "narrative", "voice_manifest.de-DE.json"), JSON.stringify(manifest, null, 2) + "\n", "utf8");
console.log(`Generated ${manifest.lines.length} German WAV voice lines`);
