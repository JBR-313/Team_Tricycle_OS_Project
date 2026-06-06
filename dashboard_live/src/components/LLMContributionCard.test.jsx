import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import LLMContributionCard from './LLMContributionCard.jsx'

// Minimal ablation fixture mirroring outputs/ablation/burst_ablation.json's
// aggregate block (the only part this card reads).
const ablation = {
  aggregate: {
    ema_cold:  { mean_mae: 7.623,  mean_pairwise_order_accuracy: 0.5,   workloads_scored: 5 },
    heuristic: { mean_mae: 4.642,  mean_pairwise_order_accuracy: 0.72,  workloads_scored: 5 },
    llm:       { mean_mae: 16.486, mean_pairwise_order_accuracy: 0.901, workloads_scored: 5 },
  },
}

describe('LLMContributionCard', () => {
  it('renders the ablation evidence with the LLM order accuracy', () => {
    render(<LLMContributionCard ablation={ablation} />)
    expect(screen.getByText(/burst-prediction ablation/i)).toBeInTheDocument()
    // 0.901 → 90% (LLM) and 0.5 → 50% (baseline). Each percentage appears in
    // both the bar and the MAE table, so assert at least one occurrence.
    expect(screen.getAllByText('90%').length).toBeGreaterThan(0)
    expect(screen.getAllByText('50%').length).toBeGreaterThan(0)
  })

  it('states the LLM-vs-baseline verdict', () => {
    render(<LLMContributionCard ablation={ablation} />)
    expect(screen.getByText(/orders bursts correctly/i)).toBeInTheDocument()
  })

  it('shows the workload count from the aggregate', () => {
    render(<LLMContributionCard ablation={ablation} />)
    expect(screen.getByText(/across 5 workloads/i)).toBeInTheDocument()
  })

  it('renders nothing when ablation data is absent (hides itself)', () => {
    const { container } = render(<LLMContributionCard ablation={null} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('renders nothing when aggregate is missing', () => {
    const { container } = render(<LLMContributionCard ablation={{}} />)
    expect(container).toBeEmptyDOMElement()
  })

  it('tolerates a partial aggregate (only llm present)', () => {
    const partial = { aggregate: { llm: { mean_mae: 16.4, mean_pairwise_order_accuracy: 0.9, workloads_scored: 5 } } }
    render(<LLMContributionCard ablation={partial} />)
    expect(screen.getAllByText('90%').length).toBeGreaterThan(0)
  })
})
