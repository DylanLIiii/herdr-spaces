import test from 'node:test';
import assert from 'node:assert/strict';
import {projectRole,projectHint} from '../mods/projects-agents/roles.js';

test('project roles reflect explicit Core labels, including a handed-off PM',()=>{
 const terminal={address:'server/t3',labels:{'projects.role':'main','projects.name':'Website'}};
 assert.equal(projectRole(terminal),'PM');assert.equal(projectHint(terminal),'PM · Website · server/t3');
 terminal.labels['projects.role']='former-main';assert.equal(projectRole(terminal),'前 PM');
 terminal.labels['projects.role']='worker';assert.equal(projectRole(terminal),'Worker');
 assert.equal(projectRole({program:{name:'PM'},status:'working'}),null);
 assert.equal(projectRole(null),null);
});
