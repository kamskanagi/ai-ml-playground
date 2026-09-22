import { TestBed } from '@angular/core/testing';

import { SignalTrace } from '../core/models';
import { ControlChart } from './control-chart';

function trace(values: number[], lcl = 45, ucl = 55): SignalTrace {
  return {
    signal_key: 'chamber_pressure',
    label: 'Chamber Pressure',
    unit: 'mTorr',
    lcl,
    ucl,
    current: {
      run_id: 9,
      started_at: '2026-09-20T10:00:00Z',
      value: values[values.length - 1],
      z_score: 3.2,
      out_of_limit: values[values.length - 1] > ucl,
    },
    history: values.map((value, i) => ({
      run_id: i,
      started_at: `2026-09-2${i}T10:00:00Z`,
      value,
      z_score: 0,
      out_of_limit: value > ucl || value < lcl,
    })),
  };
}

function render(t: SignalTrace) {
  const fixture = TestBed.createComponent(ControlChart);
  fixture.componentRef.setInput('trace', t);
  fixture.detectChanges();
  return fixture.nativeElement as HTMLElement;
}

describe('ControlChart', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({ imports: [ControlChart] }).compileComponents();
  });

  it('draws one dot per run', () => {
    const el = render(trace([50, 51, 49, 58]));
    // The last point also gets a halo when it breaches, so count only the data dots.
    expect(el.querySelectorAll('circle.dot').length).toBe(4);
  });

  it('marks the points that are outside the control limits', () => {
    const el = render(trace([50, 51, 49, 58]));
    expect(el.querySelectorAll('circle.dot.breach').length).toBe(1);
  });

  it('marks nothing when the whole series is in control', () => {
    const el = render(trace([50, 51, 49, 50]));
    expect(el.querySelectorAll('circle.dot.breach').length).toBe(0);
  });

  it('keeps a breaching point visually outside the limit line', () => {
    // The scale must cover the data and the limits, or an excursion could be
    // drawn inside the band and the chart would contradict the alarm.
    const el = render(trace([50, 51, 49, 58]));
    const dots = [...el.querySelectorAll('circle.dot')] as SVGCircleElement[];
    const breach = dots[dots.length - 1];
    const ucl = el.querySelectorAll('line.limit')[0] as SVGLineElement;
    expect(Number(breach.getAttribute('cy'))).toBeLessThan(Number(ucl.getAttribute('y1')));
  });

  it('handles a low excursion as well as a high one', () => {
    const el = render(trace([50, 51, 49, 41]));
    const dots = [...el.querySelectorAll('circle.dot')] as SVGCircleElement[];
    const lcl = el.querySelectorAll('line.limit')[1] as SVGLineElement;
    expect(Number(dots[dots.length - 1].getAttribute('cy'))).toBeGreaterThan(
      Number(lcl.getAttribute('y1')),
    );
  });

  it('survives a single-point series without dividing by zero', () => {
    const el = render(trace([58]));
    const dot = el.querySelector('circle.dot') as SVGCircleElement;
    expect(Number(dot.getAttribute('cx'))).not.toBeNaN();
    expect(Number(dot.getAttribute('cy'))).not.toBeNaN();
  });

  it('labels the reading with its value and limits', () => {
    const el = render(trace([50, 58.4]));
    expect(el.textContent).toContain('58.40');
    expect(el.textContent).toContain('limits 45–55');
  });
});
