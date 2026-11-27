import { expect, test } from 'claude-code/testing'
import type { On } from 'claude-code'

const BAND = {
  plugin: 'retro-report',
  component: 'AbovePrompt',
  props: {
    hasSurvey: false,
    isCollapsed: false,
    isWorking: false,
    maxRows: 20,
    bodyColumns: 80,
    scroll: { offset: 0, bodyRows: 20 },
    view: {},
  },
} as const

type Run = { exitCode: number; stdout: string; stderr: string }

// Stands for the engine: the environment, the script's answer, toasts and the commands run.
function engine(on: On, run: Run | Error, command: Error | null = null,
                env: Record<string, string> = { HOME: '/home/me' }) {
  const seen = { argv: [] as readonly string[], toasts: [] as string[], commands: [] as string[] }
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('env.get', (_, e) => ({ value: env[e.name] }))
  on('process.run', (_, e) => {
    seen.argv = e.argv
    if (run instanceof Error) throw run
    return { value: { ...run, isStdoutTruncated: false, isStderrTruncated: false } }
  })
  on('ui.toast', (_, e) => {
    seen.toasts.push(e.text)
    return { value: undefined }
  })
  on('command.run', (_, e) => {
    seen.commands.push(`${e.command} ${e.args}`)
    if (command) throw command
    return {}
  })
  return seen
}

const start = { cwd: '/', surface: 'terminal', isInteractive: true } as const

test('without HOME the band finds retro.py under USERPROFILE, as on Windows', async ($, on) => {
  const seen = engine(on, { exitCode: 0, stdout: '1 s-1\n', stderr: '' }, null, { USERPROFILE: 'C:/Users/me' })
  await $.session.start(start)
  expect(seen.argv).toEqual(['python3', 'C:/Users/me/.claude/skills/retro-report/scripts/retro.py', 'due'])
})

test('without HOME nor USERPROFILE the band says so and runs nothing', async ($, on) => {
  const seen = engine(on, { exitCode: 0, stdout: '1 s-1\n', stderr: '' }, null, {})
  await $.session.start(start)
  expect(seen.argv).toEqual([])
  expect(seen.toasts).toEqual(['retro-report: Error: neither HOME nor USERPROFILE is set, so retro.py cannot be found'])
})

for (const surface of ['terminal', 'desktop'] as const) {
  test(`the band shows today's count from retro.py due, on ${surface}`, async ($, on) => {
    const seen = engine(on, { exitCode: 0, stdout: '12 s-1\n', stderr: '' })
    await $.session.start(start)
    expect(seen.argv).toEqual(['python3', '/home/me/.claude/skills/retro-report/scripts/retro.py', 'due'])

    const ui = await $.ui.mount({ ...BAND, surface })
    expect((await ui.find({ type: 'Text', text: /worth a retro today/ }))?.text).toBe('12 sessions worth a retro today ')
    expect(await ui.findAll({ type: 'Button' })).toHaveLength(2)
    await ui.unmount()
  })

  test(`Generate report runs /retro-report on the first worth session, on ${surface}`, async ($, on) => {
    const seen = engine(on, { exitCode: 0, stdout: '12 s-1\n', stderr: '' })
    await $.session.start(start)
    const ui = await $.ui.mount({ ...BAND, surface })
    await ui.press({ key: 'generate' })
    expect(seen.commands).toEqual(['retro-report s-1'])
    expect(await ui.find({ type: 'Text', text: /worth a retro today/ })).toBeUndefined()
    await ui.unmount()
  })

  test(`Later hides the band without running anything, on ${surface}`, async ($, on) => {
    const seen = engine(on, { exitCode: 0, stdout: '12 s-1\n', stderr: '' })
    await $.session.start(start)
    const ui = await $.ui.mount({ ...BAND, surface })
    await ui.press({ key: 'later' })
    expect(seen.commands).toEqual([])
    expect(await ui.find({ type: 'Text', text: /worth a retro today/ })).toBeUndefined()
    await ui.unmount()
  })
}

test('one worth session reads in the singular', async ($, on) => {
  engine(on, { exitCode: 0, stdout: '1 s-1\n', stderr: '' })
  await $.session.start(start)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect((await ui.find({ type: 'Text', text: /worth a retro today/ }))?.text).toBe('1 session worth a retro today ')
  await ui.unmount()
})

test('no worth session today draws no band and no toast', async ($, on) => {
  const seen = engine(on, { exitCode: 0, stdout: '', stderr: '' })
  await $.session.start(start)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await ui.find({ type: 'Text', text: /worth a retro today/ })).toBeUndefined()
  expect(seen.toasts).toEqual([])
  await ui.unmount()
})

test('a broken config draws no band and says why in one toast', async ($, on) => {
  const seen = engine(on, { exitCode: 1, stdout: '', stderr: 'config.yaml: missing; see config.example.yaml\n' })
  await $.session.start(start)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await ui.find({ type: 'Text', text: /worth a retro today/ })).toBeUndefined()
  expect(seen.toasts).toEqual(['retro-report: config.yaml: missing; see config.example.yaml'])
  await ui.unmount()
})

test('python3 missing draws no band and says why in one toast', async ($, on) => {
  const seen = engine(on, new Error('python3: not found'))
  await $.session.start(start)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await ui.find({ type: 'Text', text: /worth a retro today/ })).toBeUndefined()
  expect(seen.toasts).toHaveLength(1)
  await ui.unmount()
})

test('a report that cannot start brings the band back and says why in a toast', async ($, on) => {
  const seen = engine(on, { exitCode: 0, stdout: '12 s-1\n', stderr: '' }, new Error('unknown command'))
  await $.session.start(start)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  await ui.press({ key: 'generate' })
  expect(seen.toasts).toHaveLength(1)
  expect(seen.toasts[0]).toMatch(/^retro-report: /)
  expect(await ui.find({ type: 'Text', text: /worth a retro today/ })).toBeDefined()
  await ui.unmount()
})

test('a line due cannot read draws no band and says why in a toast', async ($, on) => {
  const seen = engine(on, { exitCode: 0, stdout: 'twelve\n', stderr: '' })
  await $.session.start(start)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await ui.find({ type: 'Text', text: /worth a retro today/ })).toBeUndefined()
  expect(seen.toasts).toEqual(['retro-report: retro.py due printed "twelve", not a count and a session id'])
  await ui.unmount()
})
