/**
 * FeedbackBadge — compact opt-in honesty chip (safe_feedback_loop_goal §8).
 *
 * Renders NOTHING by default: the standard demo never consumes feedback rules
 * (manifest.feedback_consumed is false/absent), so the top bar is unchanged.
 *
 * It appears ONLY when a run was started with feedback consumption opted in
 * (--use-feedback / use_feedback:true), making it visible that accumulated
 * FAIL-only rules influenced THIS recommendation. This is distinct from
 * feedback GENERATION (a post-evaluation, future-learning artifact) which is
 * surfaced separately on the Evaluation tab and never claims to change the
 * current run.
 */
export default function FeedbackBadge({ manifest }) {
  const mf = manifest || {}
  if (!mf.feedback_consumed) return null
  const n = Number.isFinite(mf.feedback_rule_count) ? mf.feedback_rule_count : null
  const title =
    `Feedback consumption opted in (--use-feedback): ` +
    `${n != null ? n : 'accumulated'} FAIL-only rule(s) from ` +
    `${mf.feedback_rules_path || 'outputs/live/feedback_rules.md'} were ` +
    `injected into this recommendation prompt.`
  return (
    <span className="source-badge source-badge-feedback" title={title}>
      Feedback: ON{n != null ? ` ·${n}` : ''}
    </span>
  )
}
