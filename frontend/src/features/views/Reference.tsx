import { useEffect, useState } from 'react'

import { api } from '../../lib/api'
import type { AxisFamily } from '../../types'

interface Domain {
  label: string
  levels: { level: string; meaning: string }[]
  target?: string[]
  note?: string
}

/** The closed axis list and the three domains of learning, as reference. */
export function Reference() {
  const [families, setFamilies] = useState<AxisFamily[]>([])
  const [domains, setDomains] = useState<Record<string, Domain> | null>(null)

  useEffect(() => {
    api<AxisFamily[]>('/axes').then(setFamilies).catch(() => undefined)
    api<Record<string, Domain>>('/domains').then(setDomains).catch(() => undefined)
  }, [])

  const total = families.reduce((count, family) => count + family.axes.length, 0)
  const loading = families.length === 0

  return (
    <>
      <div className="page-head">
        <div>
          <span className="eyebrow">Framework</span>
          <h1 className="page-title">Axes &amp; domains</h1>
        </div>
        <p className="page-sub">
          The axis list is closed. Professors prune it; nobody adds to it live, so results
          stay comparable across the cohort.
        </p>
      </div>

      <section className="card panel ref-panel">
        <header className="panel-head">
          <div>
            <span className="eyebrow">Variation axes</span>
            <h2 className="panel-title">The complete closed set</h2>
          </div>
          <span className="pill">
            {loading ? 'loading…' : `${total} axes · ${families.length} families`}
          </span>
        </header>

        <div className="families">
          {families.map((family) => (
            <div className="family" key={family.id}>
              <div className="family-head">
                <h3>{family.label}</h3>
                <p>{family.description}</p>
              </div>
              <ul className="ref-axes">
                {family.axes.map((axis) => (
                  <li key={axis.id}>
                    <strong>{axis.label}</strong>
                    <span>{axis.varies}</span>
                    <em>{axis.example}</em>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </section>

      {domains && (
        <section className="card panel ref-panel">
          <header className="panel-head">
            <div>
              <span className="eyebrow">Metric capture</span>
              <h2 className="panel-title">The three domains of learning</h2>
            </div>
          </header>

          <div className="families">
            {Object.entries(domains).map(([key, domain]) => (
              <div className="family" key={key}>
                <div className="family-head">
                  <h3>{domain.label}</h3>
                  {domain.note && <p>{domain.note}</p>}
                </div>
                <ul className="ref-levels">
                  {domain.levels.map((level) => (
                    <li
                      key={level.level}
                      className={domain.target?.includes(level.level) ? 'is-target' : ''}
                    >
                      <strong>{level.level}</strong>
                      <span>{level.meaning}</span>
                    </li>
                  ))}
                </ul>
                {domain.target && (
                  <p className="ref-note">
                    Highlighted levels are where reasoning questions sit — the levels that
                    test judgement, and the ones MCQ preparation reaches least.
                  </p>
                )}
              </div>
            ))}
          </div>
        </section>
      )}
    </>
  )
}
