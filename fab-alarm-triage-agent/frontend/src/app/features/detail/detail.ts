import { DatePipe, DecimalPipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, inject, input } from '@angular/core';
import { toObservable, toSignal } from '@angular/core/rxjs-interop';
import { RouterLink } from '@angular/router';
import { of, switchMap } from 'rxjs';

import { Api } from '../../core/api';
import { ControlChart } from '../../ui/control-chart';
import { AgentPanel } from './agent-panel';

/** One alarm, in full.
 *
 * Left: what happened, led by the control charts, because the chart is the alarm. Right:
 * what the agent made of it. Facts sit in definition lists rather than a grid of cards —
 * they are readings, not objects, and boxing each one would flatten the hierarchy.
 */
@Component({
  selector: 'alarm-detail',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, DatePipe, DecimalPipe, ControlChart, AgentPanel],
  template: `
    @if (alarm(); as a) {
      <a routerLink="/alarms" class="back">← Queue</a>

      <header class="head" [attr.data-sev]="a.severity">
        <h1>{{ a.message }}</h1>
        <p class="meta mono">
          {{ a.alarm_code }} · {{ a.severity }} · {{ a.tool_id }}/{{ a.chamber }} ·
          {{ a.raised_at | date: 'MMM d, y HH:mm' }}
        </p>
      </header>

      <div class="split">
        <div class="evidence-col">
          @if (a.out_of_limit.length) {
            <section class="charts">
              @for (s of a.out_of_limit; track s.signal_key) {
                <control-chart [trace]="s" />
              }
            </section>
          } @else {
            <p class="none">No signal was outside its control limits on this run.</p>
          }

          <dl class="facts">
            <dt>Lot</dt>
            <dd class="mono">
              {{ a.lot?.lot_id ?? '—' }}
              @if (a.lot) {
                <span class="dim">
                  {{ a.lot.product }} · {{ a.lot.wafer_count }} wafers · {{ a.lot.status }}
                </span>
              }
            </dd>

            <dt>Recipe</dt>
            <dd class="mono">{{ a.recipe_name ?? '—' }}</dd>

            <dt>Last PM</dt>
            <dd class="mono" [class.overdue]="a.equipment.pm_overdue">
              @if (a.equipment.days_since_pm !== null) {
                {{ a.equipment.days_since_pm | number: '1.0-0' }} days ago
                <span class="dim">
                  interval {{ a.equipment.pm_interval_days }}d
                  @if (a.equipment.pm_overdue) {
                    · overdue by {{ a.equipment.pm_overdue_by_days | number: '1.0-0' }}d
                  }
                </span>
              } @else {
                no record
              }
            </dd>

            <dt>Tool history</dt>
            <dd class="mono">
              {{ a.equipment.alarms_last_30d }}
              {{ a.equipment.alarms_last_30d === 1 ? 'alarm' : 'alarms' }} in the prior 30 days
            </dd>
          </dl>
        </div>

        <aside><agent-panel [alarmId]="a.id" /></aside>
      </div>
    } @else {
      <p class="none">Loading alarm…</p>
    }
  `,
  styles: [
    `
      .back {
        display: inline-block;
        font-size: 13px;
        color: var(--muted);
        text-decoration: none;
        margin-bottom: 12px;
      }
      .back:hover { color: var(--ink); }

      .head {
        border-left: 4px solid var(--sev-low);
        padding-left: 14px;
        margin-bottom: 20px;
      }
      .head[data-sev='medium'] { border-left-color: var(--sev-medium); }
      .head[data-sev='high'] { border-left-color: var(--sev-high); }
      .head[data-sev='critical'] { border-left-color: var(--sev-critical); }
      h1 { font-size: 24px; font-weight: 800; letter-spacing: -0.02em; }
      .meta { font-size: 12px; color: var(--muted); margin: 4px 0 0; text-transform: capitalize; }

      .split { display: grid; grid-template-columns: 1.35fr 1fr; gap: 24px; align-items: start; }
      @media (max-width: 900px) { .split { grid-template-columns: 1fr; } }

      .charts {
        display: flex;
        flex-direction: column;
        gap: 22px;
        background: var(--surface);
        border: 1px solid var(--line);
        border-radius: var(--radius);
        padding: 16px;
      }
      .none { color: var(--muted); }

      .facts {
        display: grid;
        grid-template-columns: 120px 1fr;
        gap: 0;
        margin: 18px 0 0;
        font-size: 13.5px;
      }
      .facts dt {
        color: var(--muted);
        font-size: 12px;
        padding: 9px 0;
        border-top: 1px solid var(--line);
      }
      .facts dd { margin: 0; padding: 9px 0; border-top: 1px solid var(--line); }
      .facts dd.overdue { color: var(--limit); }
      .dim { display: block; color: var(--muted); font-size: 11.5px; }
    `,
  ],
})
export class Detail {
  private api = inject(Api);

  readonly id = input.required<string>();

  protected readonly alarm = toSignal(
    toObservable(this.id).pipe(switchMap((id) => (id ? this.api.alarm(Number(id)) : of(null)))),
  );
}
