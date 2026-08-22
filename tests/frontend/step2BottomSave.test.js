import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const studio=readFileSync(new URL("../../src/admin/DesignStudioPage.jsx",import.meta.url),"utf8");

test("Step 2 bottom transition shares the authoritative save workflow",()=>{
  assert.equal((studio.match(/onClick=\{save\}/g)||[]).length,2);
  assert.equal((studio.match(/async function save\(\)/g)||[]).length,1);
  assert.match(studio,/saveInFlightRef\.current\|\|status!=="ready"\|\|!dirty/);
  assert.match(studio,/saveInFlightRef\.current=true/);
  assert.match(studio,/finally\{saveInFlightRef\.current=false;\}/);
});

test("Step 2 bottom transition coordinates unsaved saving saved and failure states",()=>{
  assert.match(studio,/id=\{wizardStep==="brand"\?"step2-next":undefined\}/);
  assert.match(studio,/wizardStep==="brand"\?<div className="builder-next-save"/);
  assert.match(studio,/status==="saving"\?"Saving your design…":dirty\?"Unsaved changes":"Your design is saved ✓"/);
  assert.match(studio,/Your design was not saved/);
  assert.equal((studio.match(/disabled=\{status!=="ready"\|\|!dirty\}/g)||[]).length,2);
  assert.equal((studio.match(/aria-busy=\{status==="saving"\}/g)||[]).length,2);
  assert.match(studio,/disabled=\{dirty\|\|status!=="ready"\} type="button" onClick=\{onContinue\}/);
  assert.match(studio,/wizardStep==="brand"&&!dirty\?"primary-button":"secondary-button"/);
});

test("save success and failure retain one shared dirty baseline",()=>{
  assert.match(studio,/setSavedConfig\(value\.config\)/);
  assert.match(studio,/setSaveError\(""\)/);
  assert.match(studio,/catch\(error\)\{setMessage\(error\.message\);setSaveError\(error\.message\);setStatus\("ready"\);\}/);
  assert.doesNotMatch(studio,/onClick=\{[^}]*saveDesignDraft/);
});
