import {spawn} from 'node:child_process';
import {randomBytes} from 'node:crypto';
import assert from 'node:assert/strict';
const password=randomBytes(32).toString('hex');
async function check(configured,port){
 const child=spawn(process.execPath,['node_modules/next/dist/bin/next','start','--hostname','127.0.0.1','--port',String(port)],{stdio:'ignore',env:{...process.env,REQUIRE_SITE_AUTH:'true',SITE_USER:'owner',SITE_PASSWORD:configured?password:''}});
 try{
  let response;
  for(let i=0;i<100;i++){
   if(child.exitCode!==null)throw Error('Isolated test server exited');
   try{response=await fetch(`http://127.0.0.1:${port}/`);break}catch{await new Promise(r=>setTimeout(r,100))}
  }
  assert.ok(response,'Test server did not start');
  assert.equal(response.status,configured?401:503);
  if(configured){
   assert.equal((await fetch(`http://127.0.0.1:${port}/api/tips`)).status,401);
   const headers={authorization:'Basic '+Buffer.from('owner:'+password).toString('base64')};
   assert.equal((await fetch(`http://127.0.0.1:${port}/`,{headers})).status,200);
   assert.equal((await fetch(`http://127.0.0.1:${port}/api/health`)).status,200);
  }
 }finally{child.kill('SIGTERM');await new Promise(r=>child.once('exit',r))}
}
await check(true,3101);await check(false,3102);
console.log('Private site: anonymous blocked, authenticated access succeeds, health check works, missing configuration fails closed: PASS');
