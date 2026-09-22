import { DatePipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { RouterLink } from '@angular/router';

import { Api } from '../../core/api';
import { Alarm, Severity } from '../../core/models';

const SEVERITY_ORDER: Record<Severity, number> = {
  critical: 0,
  high: 1,
  medium: 2,
  low: 3,
};

/** The alarm queue.
 *
 * A dense table rather than a grid of cards: this is a scanning surface for someone
 * mid-shift who wants to find the worst thing quickly, and cards would fit four rows on
 * screen where a table fits twenty.
 */
@Component({
  selector: 'alarm-queue',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterLink, DatePipe],
  template: `
    <header class="head">
      <h1>Alarm queue</h1>
      <p class="sub">
        {{ open().length }} open ·
        {{ critical() }} critical or high
      </p>
    </header>

    @if (alarms() === undefined) {
      <p class="state">Loading the queue…</p>
    } @else if (open().length === 0) {
      <p class="state">Nothing open. Every alarm has been dispositioned.</p>
    } @else {
      <table>
        <thead>
          <tr>
            <th>Severity</th>
            <th>Alarm</th>
            <th>Tool</th>
            <th>Lot</th>
            <th>Raised</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          @for (a of open(); track a.id) {
            <tr [attr.data-sev]="a.severity">
              <td class="sev"><span class="stripe"></span>{{ a.severity }}</td>
              <td>
                <a [routerLink]="['/alarms', a.id]" class="code mono">{{ a.alarm_code }}</a>
                <span class="msg">{{ a.message }}</span>
              </td>
              <td class="mono">{{ a.tool_id }}/{{ a.chamber }}</td>
              <td class="mono">{{ a.lot_id ?? '—' }}</td>
              <td class="mono when">{{ a.raised_at | date: 'MMM d, HH:mm' }}</td>
              <td><a [routerLink]="['/alarms', a.id]" class="go">Triage</a></td>
            </tr>
          }
        </tbody>
      </table>
    }
  `,
  styles: [
    `
      .head { margin-bottom: 18px; }
      h1 { font-size: 26px; font-weight: 800; letter-spacing: -0.02em; }
      .sub { margin: 4px 0 0; color: var(--muted); font-size: 14px; }
      .state { color: var(--muted); padding: 32px 0; }

      table { width: 100%; border-collapse: collapse; }
      th {
        text-align: left;
        font-family: var(--mono);
        font-size: 11px;
        font-weight: 600;
        letter-spacing: 0.04em;
        color: var(--muted);
        padding: 0 12px 8px;
        border-bottom: 1px solid var(--line);
      }
      td {
        padding: 11px 12px;
        border-bottom: 1px solid var(--line);
        vertical-align: baseline;
      }
      tbody tr:hover { background: var(--surface); }

      .sev {
        position: relative;
        font-size: 12.5px;
        color: var(--muted);
        padding-left: 18px;
        text-transform: capitalize;
      }
      /* The stripe carries severity as shape as well as colour, so it survives a
         colour-blind reader and a glance from two metres away. */
      .stripe {
        position: absolute;
        left: 4px;
        top: 2px;
        bottom: 2px;
        width: 4px;
        border-radius: 2px;
        background: var(--sev-low);
      }
      [data-sev='medium'] .stripe { background: var(--sev-medium); }
      [data-sev='high'] .stripe { background: var(--sev-high); }
      [data-sev='critical'] .stripe { background: var(--sev-critical); }
      [data-sev='high'] .sev, [data-sev='critical'] .sev { color: var(--ink); }

      .code { display: block; font-size: 13.5px; font-weight: 600; text-decoration: none; }
      .code:hover { text-decoration: underline; }
      .msg { display: block; color: var(--muted); font-size: 13px; }
      .when { color: var(--muted); font-size: 12.5px; white-space: nowrap; }

      .go {
        font-size: 13px;
        text-decoration: none;
        border: 1px solid var(--line);
        border-radius: var(--radius);
        padding: 4px 10px;
        white-space: nowrap;
      }
      .go:hover { border-color: var(--ink); }

      @media (max-width: 720px) {
        th:nth-child(4), td:nth-child(4),
        th:nth-child(5), td:nth-child(5) { display: none; }
      }
    `,
  ],
})
export class Queue {
  private api = inject(Api);

  protected readonly alarms = toSignal(this.api.alarms());

  protected readonly open = computed(() => {
    const rows = this.alarms() ?? [];
    return [...rows].sort(
      (a, b) =>
        SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity] ||
        b.raised_at.localeCompare(a.raised_at),
    );
  });

  protected readonly critical = computed(
    () => this.open().filter((a: Alarm) => a.severity === 'critical' || a.severity === 'high').length,
  );
}
