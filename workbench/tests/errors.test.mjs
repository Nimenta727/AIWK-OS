import {test} from 'node:test';
import assert from 'node:assert/strict';
import {translateError,localizeError} from '../src/model/errors.mjs';

test('known messages translate; English UI keeps the original',()=>{
 assert.equal(translateError('Not a git project (nothing to compare against)'),'不是 Git 项目（没有可比较的内容）');
 assert.equal(localizeError('Invalid CSRF',true),'Invalid CSRF');
 assert.match(localizeError('Invalid CSRF',false),/令牌/);
});
test('messages with values keep the value',()=>{
 assert.equal(translateError('Not installed in this image: Chromium'),'本镜像未安装：Chromium');
 assert.equal(translateError('projectDir must be an integer between 1 and 5'.replace('projectDir','maxTurns')),'maxTurns 必须是 1 到 5 之间的整数');
 assert.equal(translateError('The mandate is revoked'),'这份授权的状态是 revoked，不能运行');
});
test('unknown messages are shown as a clearly labelled English original, never silently mixed',()=>{
 assert.equal(translateError('Some brand new failure'),null);
 assert.equal(localizeError('Some brand new failure',false),'（服务返回的英文原文）Some brand new failure');
 assert.equal(localizeError(undefined,false),'（服务返回的英文原文）');
});
test('whitespace around a message does not defeat the lookup',()=>{assert.equal(translateError('  Unknown job \n'),'未知的任务');});
