const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

for (const method of ['POST', 'PUT', 'PATCH', 'DELETE', 'GET']) {
    test(`secureFetch preserves prefix/body and applies CSRF to ${method}`, async () => {
        let captured;
        const context = {Headers, URL, window: {location: {href: 'https://ecos.test/ecos/', origin: 'https://ecos.test'}},
            document: {querySelector: () => ({content: 'session-bound-token'})},
            fetch: async (url, options) => {captured = {url, options}; return {ok: true};}};
        vm.createContext(context);
        vm.runInContext(fs.readFileSync(path.join(__dirname, '../static/js/security.js'), 'utf8'), context);
        await context.secureFetch('/ecos/kine/cases', {method, headers: {Accept: 'application/json'}, body: 'fixture'});
        assert.equal(captured.url, '/ecos/kine/cases');
        assert.equal(captured.options.body, 'fixture');
        assert.equal(captured.options.credentials, 'same-origin');
        assert.equal(captured.options.headers.get('Accept'), 'application/json');
        assert.equal(captured.options.headers.get('X-CSRF-Token'), method === 'GET' ? null : 'session-bound-token');
    });
}

test('secureFetch refuses an external URL without sending its session token', async () => {
    let calls = 0;
    const context = {Headers, URL, window: {location: {href: 'https://ecos.test/ecos/', origin: 'https://ecos.test'}},
        document: {querySelector: () => ({content: 'private-token'})}, fetch: async () => {calls++;}};
    vm.createContext(context);
    vm.runInContext(fs.readFileSync(path.join(__dirname, '../static/js/security.js'), 'utf8'), context);
    await assert.rejects(context.secureFetch('https://foreign.invalid/', {method: 'POST'}), /origine externe/);
    assert.equal(calls, 0);
});

// DOM doubles exercise form data and submit/error behavior, not browser geometry.
function accountUI(initial) {
    function element(tag) {
        return {tag, children: [], dataset: {}, attrs: {}, listeners: {}, value: '',
            append(...nodes) { this.children.push(...nodes); },
            setAttribute(key, value) { this.attrs[key] = value; },
            addEventListener(name, callback) { this.listeners[name] = callback; },
            showModal() { this.open = true; },
            close() { this.open = false; this.listeners.close?.(); },
            remove() { this.removed = true; }};
    }
    const descendants = node => [node, ...node.children.flatMap(descendants)];
    const body = element('body'), requests = [];
    let fail = true, refreshes = 0;
    const context = {Headers, URL,
        window: {location: {href: 'https://ecos.test/ecos/', origin: 'https://ecos.test'}},
        document: {body, createElement: element, createTextNode: text => ({text, children: []}), querySelector: () => ({content: 'token'})},
        FormData: class { constructor(form) { this.values = descendants(form).filter(n => n.name).map(n => [n.name, n.value]); } [Symbol.iterator]() { return this.values[Symbol.iterator](); } },
        getBasePath: () => '/ecos', loadAdminStudents: () => refreshes++, loadAdminTeachers: () => refreshes++,
        fetch: async (url, options) => {
            requests.push({url, options});
            const reading = !options.method || options.method === 'GET';
            return {ok: reading || !fail, json: async () => reading ? initial : fail ? {error: 'Validation refusée'} : {success: true}};
        }};
    vm.createContext(context);
    vm.runInContext(fs.readFileSync(path.join(__dirname, '../static/js/security.js'), 'utf8'), context);
    return {context, body, requests, nodes: () => descendants(body), succeed: () => {fail = false;}, refreshes: () => refreshes};
}

test('profile dialog preserves values after failure and submits unchanged field names on retry', async () => {
    const ui = accountUI({name: 'Étudiante', student_code: '123', group_name: 'A', class_name: 'Licence'});
    await ui.context.editAccountProfile('student', 7);
    const nodes = ui.nodes(), dialog = nodes.find(n => n.tag === 'dialog'), form = nodes.find(n => n.tag === 'form');
    const name = nodes.find(n => n.name === 'name'); name.value = 'Nom corrigé';
    const submit = nodes.find(n => n.type === 'submit');
    assert.equal(nodes.find(n => n.name === 'student_code').required, true);
    assert.equal(dialog.open, true);
    await form.listeners.submit({preventDefault() {}});
    assert.equal(dialog.open, true);
    assert.equal(name.value, 'Nom corrigé');
    assert.equal(submit.disabled, false);
    assert.equal(nodes.find(n => n.attrs.role === 'alert').textContent, 'Validation refusée');
    ui.succeed();
    await form.listeners.submit({preventDefault() {}});
    const request = ui.requests.at(-1);
    assert.equal(request.url, '/ecos/admin/accounts/student/7');
    assert.equal(request.options.method, 'PATCH');
    assert.deepEqual(JSON.parse(request.options.body), {name: 'Nom corrigé', student_code: '123', group_name: 'A', class_name: 'Licence'});
    assert.equal(dialog.open, false); assert.equal(dialog.removed, true); assert.equal(ui.refreshes(), 1);
});

test('teacher scope dialog retains selected student and group identifiers in its PUT', async () => {
    const ui = accountUI({students: [{id: 1, name: 'A', student_code: '11'}, {id: 2, name: 'B', student_code: '22'}], groups: ['G1'], student_ids: [1], group_names: ['G1']});
    await ui.context.editTeacherScope(9);
    const nodes = ui.nodes(), checkboxes = nodes.filter(n => n.type === 'checkbox');
    assert.deepEqual(checkboxes.map(n => n.checked), [true, false, true]);
    checkboxes[0].checked = false; checkboxes[1].checked = true;
    ui.succeed();
    await nodes.find(n => n.tag === 'form').listeners.submit({preventDefault() {}});
    const request = ui.requests.at(-1);
    assert.equal(request.url, '/ecos/admin/teachers/9/kine-scope');
    assert.equal(request.options.method, 'PUT');
    assert.deepEqual(JSON.parse(request.options.body), {student_ids: [2], group_names: ['G1']});
    assert.equal(nodes.find(n => n.tag === 'dialog').removed, true);
});
