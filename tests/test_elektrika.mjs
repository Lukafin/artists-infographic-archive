import assert from 'node:assert/strict';
import {test} from 'node:test';
import {readFileSync} from 'node:fs';
import {Script} from 'node:vm';
import {circuit} from '../interactive-src/elektrika/model.mjs';
test('teaching comparisons give exact current and power',()=>{
 assert.deepEqual(circuit(),{voltage:6,resistance:12,closed:true,current:.5,power:3});
 assert.equal(circuit({voltage:12,resistance:12}).current,1);
 assert.equal(circuit({voltage:12,resistance:12}).power,12);
 assert.equal(circuit({voltage:6,resistance:24}).current,.25);
 assert.equal(circuit({voltage:6,resistance:24}).power,1.5);
});
test('open switch and zero voltage transfer no energy at every setting',()=>{
 for(let voltage=0;voltage<=12;voltage++)for(let resistance=4;resistance<=24;resistance++){
  const open=circuit({voltage,resistance,closed:false});assert.equal(open.current,0);assert.equal(open.power,0);
  const closed=circuit({voltage,resistance});assert.ok(closed.current>=0&&closed.current<=3);assert.ok(Math.abs(closed.power-closed.current**2*resistance)<1e-12);
 }
 assert.equal(circuit({voltage:0}).power,0);
});
test('invalid settings cannot create a short-circuit or non-finite readout',()=>{
 for(const voltage of [-1,13,NaN,Infinity])assert.throws(()=>circuit({voltage}),RangeError);
 for(const resistance of [0,3,25,NaN,Infinity])assert.throws(()=>circuit({resistance}),RangeError);
});
test('standalone page has one intact executable script and finite SVG geometry',()=>{
 const doc=readFileSync(new URL('../docs/interactive/elektrika/v1/index.html',import.meta.url),'utf8');
 const site=readFileSync(new URL('../site/interactive/elektrika/v1/index.html',import.meta.url),'utf8');assert.equal(doc,site);
 const scripts=[...doc.matchAll(/<script type="module">([\s\S]*?)<\/script>/g)];assert.equal(scripts.length,1);new Script(scripts[0][1]);
 const svg=doc.match(/<svg[\s\S]*?<\/svg>/)[0];assert.doesNotMatch(svg,/NaN|undefined|Infinity/);
 assert.equal((svg.match(/id="needle-/g)||[]).length,4);assert.match(doc,/<html lang="sl">/);
});
