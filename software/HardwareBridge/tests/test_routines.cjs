const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
(async()=>{
 const {sampleRoutine}=await import('data:text/javascript;base64,'+fs.readFileSync(path.join(__dirname,'../host/ui/routines.js')).toString('base64'));
 const catalog=require('../host/ui/routines.json');
 for(const entry of Object.values(catalog)){
  const duration=entry.frames.reduce((s,f)=>s+f.seconds,0),initial=Array(8).fill(10);
  assert.deepEqual(sampleRoutine(entry.frames,initial,0),initial);
  assert.deepEqual(sampleRoutine(entry.frames,initial,1000,1,5),Array(8).fill(0));
  assert.deepEqual(sampleRoutine(entry.frames,initial,entry.frames[0].seconds/2),initial.map((x,i)=>(x+entry.frames[0].angles[i])/2));
  assert.deepEqual(sampleRoutine(entry.frames,initial,duration,1,2),Array(8).fill(0));
 }console.log('PASS routine preview: endpoints, interpolation, repeats');
})().catch(e=>{console.error(e);process.exitCode=1;});
