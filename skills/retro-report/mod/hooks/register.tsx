import { atom, read, update } from 'claude-code'
import type { Register } from 'claude-code'

import type { Due } from '../types'

// The skill's link under ~/.claude/skills, so the band runs the installed script wherever the repo lives.
const SCRIPT = '.claude/skills/retro-report/scripts/retro.py'

const due = atom({ plugin: 'retro-report', key: 'due' } as const, null as Due)
const isHidden = atom({ plugin: 'retro-report', key: 'isHidden' } as const, false)

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    const result = await next(e)
    let worth: Due = null
    try {
      // Windows keeps the home in USERPROFILE: HOME is set only by shells like Git Bash.
      const home = (await $.env.get('HOME')) || (await $.env.get('USERPROFILE'))
      if (!home) {
        throw new Error('neither HOME nor USERPROFILE is set, so retro.py cannot be found')
      }
      const run = await $.process.run(['python3', `${home}/${SCRIPT}`, 'due'])
      const out = run.stdout.trim()
      const line = /^(\d+) (\S+)$/.exec(out)
      if (run.exitCode !== 0) {
        $.ui.toast(`retro-report: ${run.stderr.trim() || `retro.py due exited ${run.exitCode}`}`)
      } else if (line?.[2]) {
        worth = { count: Number(line[1]), session: line[2] }
      } else if (out !== '') {
        $.ui.toast(`retro-report: retro.py due printed "${out}", not a count and a session id`)
      }
    } catch (err) {
      $.ui.toast(`retro-report: ${String(err)}`)
    }
    await update($, due, () => worth)
    return result
  })

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    const worth = await read($, due)
    if (e.props.hasSurvey || worth === null || (await read($, isHidden))) {
      return next(e)
    }
    const { Box, Button, Text } = $.ui.resolve(e)
    return (
      <Box>
        <Text>{worth.count} {worth.count === 1 ? 'session' : 'sessions'} worth a retro today </Text>
        <Button
          key="generate"
          label="Generate report"
          variant="primary"
          onPress={async () => {
            await update($, isHidden, () => true)
            try {
              await $.command.run({ command: 'retro-report', args: worth.session })
            } catch (err) {
              await update($, isHidden, () => false)
              $.ui.toast(`retro-report: ${String(err)}`)
            }
          }}
        />
        <Text> </Text>
        <Button key="later" label="Later" onPress={() => update($, isHidden, () => true)} />
      </Box>
    )
  })
}
