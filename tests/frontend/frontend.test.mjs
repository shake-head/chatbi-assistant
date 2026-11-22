import test from "node:test";
import assert from "node:assert/strict";

import { ApiError, errorMessage } from "../../app/static/js/api.mjs";
import { parseSseBlock, parseSseChunks } from "../../app/static/js/sse.mjs";
import { formatNumber, rowsToCsv } from "../../app/static/js/format.mjs";
import { buildBarLineOption, buildChartOption, buildPieOption } from "../../app/static/js/charts.mjs";

test("errorMessage maps known codes to Chinese", () => {
  assert.equal(errorMessage(new ApiError("x", { code: "EMAIL_ALREADY_REGISTERED" })), "该邮箱已经注册，请直接登录或更换邮箱。");
  assert.equal(errorMessage(new ApiError("x", { code: "INVALID_CREDENTIALS" })), "邮箱或密码不正确，请重新输入。");
  assert.equal(errorMessage(new ApiError("x", { code: "UNKNOWN" })), "请求失败，请稍后重试。");
});

test("errorMessage handles network errors", () => {
  assert.match(errorMessage(new TypeError("Failed to fetch")), /无法连接服务/);
});

test("parseSseBlock parses event and JSON data", () => {
  const block = 'event: status\ndata: {"stage":"planning"}\n';
  assert.deepEqual(parseSseBlock(block), { event: "status", data: { stage: "planning" } });
});

test("parseSseChunks preserves partial blocks across chunks", () => {
  const first = parseSseChunks("", 'event: status\ndata: {"stage":"pla');
  assert.deepEqual(first.events, []);
  assert.equal(first.remainder, 'event: status\ndata: {"stage":"pla');

  const second = parseSseChunks(first.remainder, 'nning"}\n\nevent: final\ndata: {"ok":true}\n\n');
  assert.equal(second.events.length, 2);
  assert.equal(second.events[0].event, "status");
  assert.equal(second.events[1].event, "final");
});

test("rowsToCsv adds BOM and escapes dangerous cells", () => {
  const csv = rowsToCsv([
    { a: "=1+1", b: "hello,world", c: 'quote"inside' },
    { a: 1, b: null, c: "中文" },
  ]);
  assert.ok(csv.startsWith("\uFEFF"));
  assert.match(csv, /'=1\+1/);
  assert.match(csv, /"hello,world"/);
  assert.match(csv, /"quote""inside"/);
});

test("formatNumber localizes numbers", () => {
  assert.equal(formatNumber(1234.5), "1,234.5");
  assert.equal(formatNumber(null), "—");
});

test("chart options map bar, line, and pie specs", () => {
  const bar = buildBarLineOption({ x_data: ["华东", "华南"], series: [{ name: "amount", data: [1, 2] }] }, "bar");
  assert.equal(bar.series[0].type, "bar");

  const line = buildChartOption({ type: "line", x_data: ["1月"], series: [{ name: "a", data: [1] }] });
  assert.equal(line.series[0].type, "line");

  const pie = buildPieOption({ title: "占比", data: [{ name: "华东", value: 2 }] });
  assert.equal(pie.series[0].type, "pie");

  assert.equal(buildChartOption({ type: "table", title: "表" }), null);
});
