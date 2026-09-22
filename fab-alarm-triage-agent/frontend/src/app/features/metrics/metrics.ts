import { DecimalPipe, PercentPipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';

import { Api } from '../../core/api';
import { ACTION_LABEL, Action } from '../../core/models';

const ACTIONS: Action[] = ['hold_lot', 'continue', 'escalate'];

/** How the agent is doing.
 *
 * Led by the unsafe-continue figure rather than by accuracy: the two mistakes are not
 * equally expensive, and a single accuracy number hides the one that scraps wafers.
 */
@Component({
  selector: 'metrics-page',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [PercentPipe, DecimalPipe],
  template: `
    <h1>How it's doing</h1>

    @if (data(); as d) {
      @if (d.report; as r) {
        <p class="sub">
          Scored on {{ r.n }} held-out alarms the agent has never seen · {{ r.model }}
        </p>

        <section class="headline" [class.bad]="r.unsafe_continue_rate > 0.1">
          <p class="figure mono">{{ r.unsafe_continue_rate | percent: '1.0-1' }}</p>
          <p class="what">
            of lots that should have been held were marked <strong>continue</strong>
          </p>
          <p class="why">
            {{ r.unsafe_continue_count }} of
            {{ holdCases(r) }} hold cases. This is the mistake that scraps wafers, so it is
            reported on its own rather than averaged into accuracy.
          </p>
        </section>

        <dl class="figures">
          <div>
            <dt>Action accuracy</dt>
            <dd class="mono">{{ r.action_accuracy | percent: '1.0-1' }}</dd>
          </div>
          <div>
            <dt>On ambiguous codes</dt>
            <dd class="mono">{{ r.ambiguous_accuracy | percent: '1.0-1' }}</dd>
            <dd class="note">{{ r.ambiguous_n }} cases the alarm code can't answer</dd>
          </div>
          <div>
            <dt>Root cause</dt>
            <dd class="mono">{{ r.cause_accuracy | percent: '1.0-1' }}</dd>
          </div>
          <div>
            <dt>Cited 2+ evidence</dt>
            <dd class="mono">{{ r.evidence_citation_rate | percent: '1.0-1' }}</dd>
          </div>
          <div>
            <dt>Mean tool calls</dt>
            <dd class="mono">{{ r.mean_tool_calls | number: '1.1-1' }}</dd>
          </div>
          <div>
            <dt>Mean latency</dt>
            <dd class="mono">{{ r.mean_latency_ms / 1000 | number: '1.1-1' }}s</dd>
          </div>
        </dl>

        <section>
          <h2>What it confused with what</h2>
          <table class="confusion">
            <thead>
              <tr>
                <th>should be ↓ &nbsp; said →</th>
                @for (a of actions; track a) { <th>{{ ACTION_LABEL[a] }}</th> }
              </tr>
            </thead>
            <tbody>
              @for (expected of actions; track expected) {
                <tr>
                  <th>{{ ACTION_LABEL[expected] }}</th>
                  @for (predicted of actions; track predicted) {
                    <td
                      class="mono"
                      [class.hit]="expected === predicted && r.confusion[expected][predicted] > 0"
                      [class.unsafe]="expected === 'hold_lot' && predicted === 'continue'
                        && r.confusion[expected][predicted] > 0"
                    >
                      {{ r.confusion[expected][predicted] }}
                    </td>
                  }
                </tr>
              }
            </tbody>
          </table>
        </section>

        <section>
          <h2>By fault type</h2>
          <table class="scenarios">
            <thead>
              <tr><th>Scenario</th><th>Cases</th><th>Action</th><th>Root cause</th></tr>
            </thead>
            <tbody>
              @for (row of scenarios(); track row.name) {
                <tr>
                  <td class="mono">{{ row.name }}</td>
                  <td class="mono">{{ row.n }}</td>
                  <td class="mono">{{ row.action_accuracy | percent: '1.0-0' }}</td>
                  <td class="mono">{{ row.cause_accuracy | percent: '1.0-0' }}</td>
                </tr>
              }
            </tbody>
          </table>
        </section>
      } @else {
        <p class="empty">
          No evaluation has been run yet. Run <code>make eval</code> to score the agent against
          the held-out alarms.
        </p>
      }

      <section>
        <h2>What engineers did</h2>
        @if (d.live.decided === 0) {
          <p class="empty">No recommendations have been reviewed yet.</p>
        } @else {
          <p class="sub">
            {{ d.live.decided }} reviewed · {{ d.live.pending }} waiting
          </p>
          <dl class="figures">
            <div>
              <dt>Approved as proposed</dt>
              <dd class="mono">{{ d.live.agreement_rate | percent: '1.0-1' }}</dd>
            </div>
            <div><dt>Approved</dt><dd class="mono">{{ d.live.approved }}</dd></div>
            <div><dt>Edited</dt><dd class="mono">{{ d.live.edited }}</dd></div>
            <div><dt>Rejected</dt><dd class="mono">{{ d.live.rejected }}</dd></div>
          </dl>
        }
      </section>
    } @else {
      <p class="empty">Loading…</p>
    }
  `,
  styles: [
    `
      h1 { font-size: 26px; font-weight: 800; letter-spacing: -0.02em; }
      h2 { font-size: 16px; font-weight: 600; margin-bottom: 10px; }
      .sub { color: var(--muted); font-size: 14px; margin: 4px 0 20px; }
      .empty { color: var(--muted); }
      section { margin-bottom: 30px; }

      /* The one figure allowed to shout. */
      .headline {
        background: var(--surface);
        border: 1px solid var(--line);
        border-left: 5px solid var(--nominal);
        border-radius: var(--radius);
        padding: 18px 20px;
        margin-bottom: 24px;
      }
      .headline.bad { border-left-color: var(--limit); }
      .figure {
        font-family: var(--display);
        font-size: 44px;
        font-weight: 800;
        line-height: 1;
        margin: 0;
        color: var(--nominal);
      }
      .headline.bad .figure { color: var(--limit); }
      .what { font-size: 15px; margin: 6px 0 0; }
      .why { font-size: 13px; color: var(--muted); margin: 8px 0 0; max-width: 62ch; }

      .figures {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
        gap: 0 24px;
        margin: 0 0 8px;
      }
      .figures div { border-top: 1px solid var(--line); padding: 10px 0; }
      dt { font-size: 12px; color: var(--muted); }
      dd { margin: 2px 0 0; font-size: 20px; }
      dd.note { font-size: 11.5px; color: var(--muted); }

      table { border-collapse: collapse; }
      th, td { padding: 7px 14px; border-bottom: 1px solid var(--line); text-align: left; }
      thead th {
        font-family: var(--mono);
        font-size: 11px;
        font-weight: 600;
        color: var(--muted);
      }
      tbody th { font-size: 13px; font-weight: 500; }
      .confusion td { text-align: center; }
      .confusion td.hit { color: var(--nominal); font-weight: 600; }
      .confusion td.unsafe { color: var(--limit); font-weight: 600; }
    `,
  ],
})
export class MetricsPage {
  private api = inject(Api);

  protected readonly ACTION_LABEL = ACTION_LABEL;
  protected readonly actions = ACTIONS;
  protected readonly data = toSignal(this.api.metrics());

  protected readonly scenarios = computed(() => {
    const report = this.data()?.report;
    if (!report) return [];
    return Object.entries(report.per_scenario).map(([name, stats]) => ({ name, ...stats }));
  });

  protected holdCases(report: { confusion: Record<string, Record<string, number>> }): number {
    return Object.values(report.confusion['hold_lot'] ?? {}).reduce((a, b) => a + b, 0);
  }
}
