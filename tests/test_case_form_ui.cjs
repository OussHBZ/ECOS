// Exercise the actual form submit handlers without a browser dependency.
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function setup(fetch) {
    const handlers = [];
    const button = {disabled: false};
    const status = {textContent: '', classList: {remove() {}}, focus() {}, scrollIntoView() {}};
    const fields = {case_number: 'KINE-001', title: 'Saisie à conserver'};
    const form = {
        action: '/ecos/kine/cases', dataset: {},
        addEventListener(name, handler) { if (name === 'submit') handlers.push(handler); },
        querySelector(selector) { return selector === '[data-case-save-status]' ? status : null; },
        querySelectorAll(selector) { return selector === 'button[type="submit"]' ? [button] : []; },
        checkValidity() { return true; }, reportValidity() { return true; },
    };
    let ready;
    let redirected;
    const context = {
        console, fetch,
        FormData: class { constructor() { this.fields = {...fields}; } },
        document: {
            querySelector(selector) { return selector === '[data-kine-case-form]' ? form : null; },
            querySelectorAll() { return []; },
            addEventListener(name, handler) { if (name === 'DOMContentLoaded') ready = handler; },
        },
        window: {addEventListener() {}, location: {assign(url) { redirected = url; }}},
    };
    vm.runInNewContext(fs.readFileSync(path.join(__dirname, '../static/js/kine-components.js'), 'utf8'), context);
    ready();
    return {
        fields, status, button, get redirected() { return redirected; },
        async submit() {
            const event = {defaultPrevented: false, preventDefault() { this.defaultPrevented = true; }};
            for (const handler of handlers) await handler(event);
        },
    };
}

test('duplicate case stays in the form and preserves entered values', async () => {
    const ui = setup(async () => ({ok: false, status: 409, json: async () => ({error: 'Ce numéro existe déjà.'})}));
    await ui.submit();
    assert.match(ui.status.textContent, /Ce numéro existe déjà/);
    assert.equal(ui.fields.title, 'Saisie à conserver');
    assert.equal(ui.redirected, undefined);
    assert.equal(ui.button.disabled, false);
});

test('expired session response preserves the form and allows retry', async () => {
    const ui = setup(async () => ({ok: true, status: 200, json: async () => { throw new Error('HTML login page'); }}));
    await ui.submit();
    assert.match(ui.status.textContent, /session a expiré/);
    assert.equal(ui.fields.case_number, 'KINE-001');
    assert.equal(ui.button.disabled, false);
});

test('double submit sends one request and follows the server prefix on success', async () => {
    let finish;
    let calls = 0;
    const ui = setup(() => { calls++; return new Promise(resolve => { finish = resolve; }); });
    const pending = ui.submit();
    await Promise.resolve();
    await ui.submit();
    assert.equal(calls, 1);
    assert.equal(ui.button.disabled, true);
    finish({ok: true, status: 201, json: async () => ({redirect_url: '/ecos/kine/cases/42'})});
    await pending;
    assert.equal(ui.redirected, '/ecos/kine/cases/42');
});
