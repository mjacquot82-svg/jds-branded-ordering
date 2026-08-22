import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const studio=readFileSync(new URL("../../src/admin/DesignStudioPage.jsx",import.meta.url),"utf8");
const styles=readFileSync(new URL("../../src/style.css",import.meta.url),"utf8");

test("hydration settles Step 2 into retryable ready or explicit error state",()=>{
  assert.match(studio,/Promise\.all\(\[fetchDesignDraft\(\),fetchDesignVersions\(\),fetchMedia\(\),fetchReadiness\(\)\]\)/);
  assert.match(studio,/setStatus\("ready"\)/);assert.match(studio,/setStatus\("error"\)/);
  assert.doesNotMatch(studio,/setStatus\("loading"\)[\s\S]*finally/);
});

test("dirty save controls depend on real request state rather than contrast feedback",()=>{
  assert.equal((studio.match(/disabled=\{status!=="ready"\|\|!dirty\}/g)||[]).length,2);
  assert.doesNotMatch(studio,/disabled=\{status!=="ready"\|\|!dirty\|\|!contrastValid\}/);
  assert.match(studio,/setSaveError\(error\.message\);setStatus\("ready"\)/);
  assert.match(studio,/saveInFlightRef\.current/);
});

test("busy cursor is reserved for actual requests",()=>{
  assert.match(styles,/\.primary-button:disabled,[\s\S]*?cursor: not-allowed/);
  assert.match(styles,/\.primary-button\[aria-busy="true"\],[\s\S]*?cursor: progress/);
  assert.equal((studio.match(/aria-busy=\{status==="saving"\}/g)||[]).length,2);
});

test("contrast remains authoritative while the merchant error explains the remedy",()=>{
  assert.match(studio,/contrast\(config\.colors\.text,config\.colors\.background\)>=4\.5/);
  assert.match(studio,/contrast\(config\.colors\.text,config\.colors\.surface\)>=4\.5/);
  assert.match(studio,/This text colour may be difficult for customers to read/);
  assert.match(studio,/Choose a darker colour or Reset to layout colours before saving/);
  assert.match(studio,/resetToLayoutColors/);
  assert.match(studio,/>Reset to layout colours<\/button>/);
  assert.doesNotMatch(studio,/Text needs at least 4\.5:1 contrast/);
});
