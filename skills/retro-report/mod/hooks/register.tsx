import { atom, read, update } from 'claude-code'
import type { Register } from 'claude-code'

// The skill's link under ~/.claude/skills, so the band runs the installed script wherever the repo lives.
const SCRIPT = '.claude/skills/retro-report/scripts/retro.py'

const due = atom({ plugin: 'retro-report', key: 'due' } as const, null)
const isHidden = atom({ plugin: 'retro-report', key: 'isHidden' } as const, false)

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    const result = await next(e)
    let count: number | null = null
    try {
      const home = await $.env.get('HOME')
      const run = await $.process.run(['python3', `${home}/${SCRIPT}`, 'due'])
      if (run.exitCode === 0) {
        count = run.stdout.trim() === '' ? null : Number(run.stdout.trim())
      } else {
        $.ui.toast(`retro-report: ${run.stderr.trim() || `retro.py due exited ${run.exitCode}`}`)
      }
    } catch (err) {
      $.ui.toast(`retro-report: ${String(err)}`)
    }
    await update($, due, () => count)
    return result
  })

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const count = await read($, due)
    if (e.props.hasSurvey || count === null || (await read($, isHidden))) {
      return next(e)
    }
    const { Box, Button, Text } = $.ui.resolve(e)
    return (
      <Box>
        <Text>{count} sessions wait for a retro </Text>
        <Button
          key="generate"
          label="Generate report"
          variant="primary"
          onPress={async () => {
            await update($, isHidden, () => true)
            await $.command.run({ command: 'retro-report' })
          }}
        />
        <Text> </Text>
        <Button key="later" label="Later" onPress={() => update($, isHidden, () => true)} />
      </Box>
    )
  })
}
