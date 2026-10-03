import { postJson } from './client'
import type { DqIssueReviewRow } from '../types/views'

export function reviewDqIssue(
  issueId: number, decision: DqIssueReviewRow['decision'], reviewer: string, note: string,
): Promise<{ issue_id: number; review_id: number; decision: string }> {
  return postJson('/dq-issues/review', { issue_id: issueId, decision, reviewer, note })
}
