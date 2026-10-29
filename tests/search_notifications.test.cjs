const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync('web/design.js', 'utf8');

test('empty search results and warnings use the bottom notification', async () => {
  const nodes = new Map();
  const notifications = [];
  const $ = selector => {
    if (!nodes.has(selector)) nodes.set(selector, {value:'', textContent:'', hidden:true,
      replaceChildren(){}, append(){}, setAttribute(){}});
    return nodes.get(selector);
  };
  $('#order-search-query').value = 'MISSING';
  const context = {$, URLSearchParams, searchRequest:0, searchOffset:0, activeSearch:null,
    api:async () => ({groups:[], total:0, next_offset:null, warnings:['Test warning']}),
    notify:(...args) => notifications.push(args), renderOrderOccurrence(){}};
  vm.createContext(context);
  await vm.runInContext(source.slice(source.indexOf('async function searchOrders('),
    source.indexOf("$('#order-search-form').addEventListener")) + '\nsearchOrders()', context);
  assert.equal($('#order-search-status').textContent, '');
  assert.match(notifications[0][0], /No matching order groups/);
  assert.match(notifications[0][0], /Test warning/);
  assert.equal($('#search-progress').hidden, true);
});
