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

// Stands for the engine: HOME, the script's answer, toasts and the commands run.
function engine(on: On, run: Run | Error) {
  const seen = { argv: [] as readonly string[], toasts: [] as string[], commands: [] as string[] }
  on('session.start', (_, e) => ({ cwd: e.cwd }))
  on('env.get', () => ({ value: '/home/me' }))
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
    seen.commands.push(e.command)
    return {}
  })
  return seen
}

const start = { cwd: '/', surface: 'terminal', isInteractive: true } as const

for (const surface of ['terminal', 'desktop'] as const) {
  test(`the band shows the count from retro.py due, on ${surface}`, async ($, on) => {
    const seen = engine(on, { exitCode: 0, stdout: '12\n', stderr: '' })
    await $.session.start(start)
    expect(seen.argv).toEqual(['python3', '/home/me/.claude/skills/retro-report/scripts/retro.py', 'due'])

    const ui = await $.ui.mount({ ...BAND, surface })
    expect((await ui.find({ type: 'Text', text: /sessions wait/ }))?.text).toBe('12 sessions wait for a retro ')
    expect(await ui.findAll({ type: 'Button' })).toHaveLength(2)
    await ui.unmount()
  })

  test(`Generate report runs /retro-report and hides the band, on ${surface}`, async ($, on) => {
    const seen = engine(on, { exitCode: 0, stdout: '12\n', stderr: '' })
    await $.session.start(start)
    const ui = await $.ui.mount({ ...BAND, surface })
    await ui.press({ key: 'generate' })
    expect(seen.commands).toEqual(['retro-report'])
    expect(await ui.find({ type: 'Text', text: /sessions wait/ })).toBeUndefined()
    await ui.unmount()
  })

  test(`Later hides the band without running anything, on ${surface}`, async ($, on) => {
    const seen = engine(on, { exitCode: 0, stdout: '12\n', stderr: '' })
    await $.session.start(start)
    const ui = await $.ui.mount({ ...BAND, surface })
    await ui.press({ key: 'later' })
    expect(seen.commands).toEqual([])
    expect(await ui.find({ type: 'Text', text: /sessions wait/ })).toBeUndefined()
    await ui.unmount()
  })
}

test('below the threshold there is no band and no toast', async ($, on) => {
  const seen = engine(on, { exitCode: 0, stdout: '', stderr: '' })
  await $.session.start(start)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await ui.find({ type: 'Text', text: /sessions wait/ })).toBeUndefined()
  expect(seen.toasts).toEqual([])
  await ui.unmount()
})

test('a broken config draws no band and says why in one toast', async ($, on) => {
  const seen = engine(on, { exitCode: 1, stdout: '', stderr: 'config.yaml: missing; see config.example.yaml\n' })
  await $.session.start(start)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await ui.find({ type: 'Text', text: /sessions wait/ })).toBeUndefined()
  expect(seen.toasts).toEqual(['retro-report: config.yaml: missing; see config.example.yaml'])
  await ui.unmount()
})

test('python3 missing draws no band and says why in one toast', async ($, on) => {
  const seen = engine(on, new Error('python3: not found'))
  await $.session.start(start)
  const ui = await $.ui.mount({ ...BAND, surface: 'terminal' })
  expect(await ui.find({ type: 'Text', text: /sessions wait/ })).toBeUndefined()
  expect(seen.toasts).toHaveLength(1)
  await ui.unmount()
})
