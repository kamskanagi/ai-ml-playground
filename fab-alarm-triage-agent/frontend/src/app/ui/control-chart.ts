import { DecimalPipe } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

import { SignalTrace } from '../core/models';

interface Plotted {
  x: number;
  y: number;
  value: number;
  breach: boolean;
  last: boolean;
}

const W = 680;
const H = 190;
// `right` must hold the reading callout ("2.67" over "sccm · +5.00σ"), not just the
// plot. Sized to the longest unit-and-sigma line so it never clips at the card edge.
const PAD = { left: 56, right: 108, top: 18, bottom: 26 };

/** An SPC control chart for one signal.
 *
 * This is the chart an engineer already reads on the tool: a centre line, two control
 * limits, and one dot per run. It is the hero of the alarm view because the shape of the
 * series — a steady climb, a lone spike, a flat repeat — is the evidence, far more than
 * the single number that tripped the alarm.
 */
@Component({
  selector: 'control-chart',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [DecimalPipe],
  template: `
    <figure>
      <figcaption>
        <span class="label">{{ trace().label }}</span>
        <span class="mono spec">
          limits {{ trace().lcl }}–{{ trace().ucl }} {{ trace().unit }}
        </span>
      </figcaption>

      <svg [attr.viewBox]="'0 0 ' + W + ' ' + H" role="img" [attr.aria-label]="summary()">
        <!-- control limits -->
        <line [attr.x1]="PAD.left" [attr.x2]="W - PAD.right" [attr.y1]="uclY()" [attr.y2]="uclY()"
              class="limit" />
        <line [attr.x1]="PAD.left" [attr.x2]="W - PAD.right" [attr.y1]="lclY()" [attr.y2]="lclY()"
              class="limit" />
        <line [attr.x1]="PAD.left" [attr.x2]="W - PAD.right" [attr.y1]="midY()" [attr.y2]="midY()"
              class="centre" />

        <text [attr.x]="PAD.left - 8" [attr.y]="uclY() + 4" class="axis ucl">{{ trace().ucl }}</text>
        <text [attr.x]="PAD.left - 8" [attr.y]="lclY() + 4" class="axis ucl">{{ trace().lcl }}</text>

        <!-- series -->
        <polyline [attr.points]="line()" class="series" />

        @for (p of points(); track p.x) {
          <circle [attr.cx]="p.x" [attr.cy]="p.y" [attr.r]="p.last ? 5 : 3.5"
                  [class.breach]="p.breach" class="dot" />
          @if (p.last && p.breach) {
            <circle [attr.cx]="p.x" [attr.cy]="p.y" r="10" class="halo" />
          }
        }

        <!-- current reading -->
        <text [attr.x]="W - PAD.right + 12" [attr.y]="lastY() - 2" class="reading">
          {{ current().value | number: '1.2-2' }}
        </text>
        <text [attr.x]="W - PAD.right + 12" [attr.y]="lastY() + 13" class="axis">
          {{ trace().unit }} · {{ signed(current().z_score) }}σ
        </text>

        <text [attr.x]="PAD.left" [attr.y]="H - 6" class="axis">oldest</text>
        <text [attr.x]="W - PAD.right" [attr.y]="H - 6" class="axis end">this run</text>
      </svg>
    </figure>
  `,
  styles: [
    `
      figure { margin: 0; }
      figcaption {
        display: flex;
        justify-content: space-between;
        align-items: baseline;
        gap: 12px;
        margin-bottom: 4px;
      }
      .label { font-family: var(--display); font-weight: 600; font-size: 14px; }
      .spec { font-size: 11.5px; color: var(--muted); }
      svg { display: block; width: 100%; height: auto; overflow: visible; }

      .limit { stroke: var(--limit); stroke-width: 1.4; stroke-dasharray: 7 4; }
      .centre { stroke: var(--nominal); stroke-width: 1.4; }
      .series { fill: none; stroke: var(--muted); stroke-width: 2; stroke-linejoin: round; }
      .dot { fill: var(--muted); }
      .dot.breach { fill: var(--limit); }
      .halo { fill: none; stroke: var(--limit); stroke-width: 1.4; opacity: 0.45; }

      .axis {
        font-family: var(--mono);
        font-size: 10.5px;
        fill: var(--muted);
      }
      .axis.ucl { fill: var(--limit); text-anchor: end; }
      .axis.end { text-anchor: end; }
      .reading {
        font-family: var(--mono);
        font-size: 15px;
        font-weight: 600;
        fill: var(--limit);
      }
    `,
  ],
})
export class ControlChart {
  readonly trace = input.required<SignalTrace>();

  protected readonly W = W;
  protected readonly H = H;
  protected readonly PAD = PAD;

  protected readonly current = computed(() => this.trace().current);

  /** Scale covers the data and both limits, so a breach is always visibly outside. */
  private readonly bounds = computed(() => {
    const t = this.trace();
    const values = t.history.map((p) => p.value);
    const lo = Math.min(...values, t.lcl);
    const hi = Math.max(...values, t.ucl);
    const pad = (hi - lo || 1) * 0.18;
    return { lo: lo - pad, hi: hi + pad };
  });

  private y(value: number): number {
    const { lo, hi } = this.bounds();
    const usable = H - PAD.top - PAD.bottom;
    return PAD.top + usable - ((value - lo) / (hi - lo)) * usable;
  }

  protected readonly points = computed<Plotted[]>(() => {
    const t = this.trace();
    const n = t.history.length;
    const span = W - PAD.left - PAD.right;
    return t.history.map((p, i) => ({
      x: PAD.left + (n === 1 ? span : (i / (n - 1)) * span),
      y: this.y(p.value),
      value: p.value,
      breach: p.value > t.ucl || p.value < t.lcl,
      last: i === n - 1,
    }));
  });

  protected readonly line = computed(() =>
    this.points()
      .map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`)
      .join(' '),
  );

  protected readonly uclY = computed(() => this.y(this.trace().ucl));
  protected readonly lclY = computed(() => this.y(this.trace().lcl));
  protected readonly midY = computed(() => this.y((this.trace().lcl + this.trace().ucl) / 2));
  protected readonly lastY = computed(() => this.y(this.current().value));

  protected readonly summary = computed(() => {
    const t = this.trace();
    return `${t.label}: ${t.current.value.toFixed(2)} ${t.unit}, limits ${t.lcl} to ${t.ucl}`;
  });

  protected signed(z: number): string {
    return `${z >= 0 ? '+' : ''}${z.toFixed(2)}`;
  }
}
