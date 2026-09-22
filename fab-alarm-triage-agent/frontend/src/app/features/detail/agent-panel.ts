import { DecimalPipe } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  inject,
  input,
  signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';

import { Api } from '../../core/api';
import { Engineer } from '../../core/engineer';
import { ACTION_LABEL, Action, AgentRun, AgentStep, ReviewDecision } from '../../core/models';

const POLL_MS = 1500;

/** The agent's side of the alarm view: run it, watch it work, decide on what it says. */
@Component({
  selector: 'agent-panel',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [FormsModule, DecimalPipe],
  template: `
    <section class="panel">
      <h2>Triage</h2>

      @if (!run()) {
        <p class="idle">
          No investigation yet. The agent will gather sensor history, equipment state, recent
          recipe changes and past incidents, then recommend a disposition for you to decide on.
        </p>
        <button class="primary" (click)="start()" [disabled]="busy()">
          {{ busy() ? 'Starting…' : 'Run triage' }}
        </button>
        @if (error()) { <p class="error">{{ error() }}</p> }
      } @else {
        <div class="status mono" [attr.data-status]="run()!.status">
          {{ statusLabel(run()!) }}
        </div>

        <!-- The trace is a genuine sequence, so it is numbered. -->
        <ol class="timeline">
          @for (s of steps(); track s.seq) {
            <li>
              <span class="seq mono">{{ s.seq }}</span>
              <div>
                <span class="node">{{ s.tool_name ?? s.node }}</span>
                @if (s.latency_ms !== null) {
                  <span class="ms mono">{{ s.latency_ms }} ms</span>
                }
                @if (s.tool_args) {
                  <code class="args">{{ compact(s.tool_args) }}</code>
                }
                @if (s.error) { <span class="step-error">{{ s.error }}</span> }
              </div>
            </li>
          }
        </ol>

        @if (run()!.disposition; as d) {
          <article class="proposal" [attr.data-action]="d.recommended_action">
            <div class="verdict">
              <span class="action">{{ ACTION_LABEL[d.recommended_action] }}</span>
              <span class="conf mono">{{ d.confidence | number: '1.0-2' }} confidence</span>
            </div>
            @if (d.root_cause_category) {
              <p class="cause mono">{{ d.root_cause_category }}</p>
            }
            <p class="hypothesis">{{ d.hypothesis }}</p>

            @if (d.evidence.length) {
              <dl class="evidence">
                @for (e of d.evidence; track e.ref) {
                  <dt class="mono">{{ e.ref }}</dt>
                  <dd>{{ e.detail }}</dd>
                }
              </dl>
            } @else {
              <p class="no-evidence">No evidence cited. Treat this recommendation with caution.</p>
            }

            @if (d.status === 'pending') {
              <div class="review">
                <label>
                  Note
                  <input [(ngModel)]="note" placeholder="Optional, kept with the decision" />
                </label>
                <div class="actions">
                  <button class="approve" (click)="decide('approve')" [disabled]="busy()">
                    Approve
                  </button>
                  <select [(ngModel)]="editAction" aria-label="Replace the recommended action">
                    <option value="hold_lot">Hold lot</option>
                    <option value="continue">Continue</option>
                    <option value="escalate">Escalate</option>
                  </select>
                  <button (click)="decide('edit')" [disabled]="busy()">Use this instead</button>
                  <button class="reject" (click)="decide('reject')" [disabled]="busy()">
                    Reject
                  </button>
                </div>
              </div>
            } @else {
              <p class="decided">
                <span>{{ decidedLabel(d.status) }} by {{ d.engineer_name }}</span>@if (
                  d.final_action
                ) {<span>, recorded as <strong>{{ ACTION_LABEL[d.final_action] }}</strong></span>}<span>.</span>
                @if (d.engineer_note) { <span class="note-back">“{{ d.engineer_note }}”</span> }
              </p>
            }
          </article>
        }

        @if (run()!.error) { <p class="error">{{ run()!.error }}</p> }
        @if (error()) { <p class="error">{{ error() }}</p> }
      }
    </section>
  `,
  styles: [
    `
      .panel {
        background: var(--surface);
        border: 1px solid var(--line);
        border-radius: var(--radius);
        padding: 18px;
      }
      h2 { font-size: 17px; font-weight: 600; margin-bottom: 10px; }
      .idle { color: var(--muted); font-size: 14px; margin: 0 0 14px; }

      button {
        border: 1px solid var(--line);
        background: var(--surface);
        color: var(--ink);
        border-radius: var(--radius);
        padding: 7px 14px;
      }
      button:hover:not(:disabled) { border-color: var(--ink); }
      button:disabled { opacity: 0.5; cursor: default; }
      button.primary { background: var(--ink); color: var(--ground); border-color: var(--ink); }

      .status {
        font-size: 11.5px;
        color: var(--muted);
        padding-bottom: 10px;
        border-bottom: 1px solid var(--line);
      }
      .status[data-status='awaiting_review'] { color: var(--hold); }
      .status[data-status='failed'] { color: var(--limit); }

      .timeline { list-style: none; margin: 12px 0; padding: 0; }
      .timeline li { display: grid; grid-template-columns: 26px 1fr; gap: 8px; padding: 5px 0; }
      .seq { font-size: 11px; color: var(--muted); }
      .node { font-size: 13.5px; font-weight: 500; }
      .ms { font-size: 11px; color: var(--muted); margin-left: 8px; }
      .args {
        display: block;
        font-family: var(--mono);
        font-size: 11px;
        color: var(--muted);
        overflow-wrap: anywhere;
      }
      .step-error { display: block; font-size: 11.5px; color: var(--limit); }

      /* The one place the panel raises its voice. */
      .proposal {
        border-top: 3px solid var(--muted);
        background: var(--sunken);
        border-radius: var(--radius);
        padding: 14px;
        margin-top: 10px;
      }
      .proposal[data-action='hold_lot'] { border-top-color: var(--hold); }
      .proposal[data-action='continue'] { border-top-color: var(--continue); }
      .proposal[data-action='escalate'] { border-top-color: var(--escalate); }

      .verdict { display: flex; align-items: baseline; justify-content: space-between; gap: 10px; }
      .action { font-family: var(--display); font-size: 19px; font-weight: 800; }
      [data-action='hold_lot'] .action { color: var(--hold); }
      [data-action='continue'] .action { color: var(--continue); }
      [data-action='escalate'] .action { color: var(--escalate); }
      .conf { font-size: 11.5px; color: var(--muted); }
      .cause { font-size: 11.5px; color: var(--muted); margin: 2px 0 8px; }
      .hypothesis { font-size: 14px; margin: 0 0 12px; }

      .evidence { margin: 0; font-size: 13px; }
      .evidence dt { font-size: 11.5px; color: var(--muted); margin-top: 7px; }
      .evidence dd { margin: 1px 0 0; }
      .no-evidence { font-size: 13px; color: var(--limit); margin: 0; }

      .review { margin-top: 14px; border-top: 1px solid var(--line); padding-top: 12px; }
      label { display: block; font-size: 11.5px; color: var(--muted); }
      input, select {
        font-family: inherit;
        font-size: 13.5px;
        color: var(--ink);
        background: var(--surface);
        border: 1px solid var(--line);
        border-radius: var(--radius);
        padding: 6px 8px;
      }
      input { width: 100%; margin-top: 3px; }
      .actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 10px; }
      .approve { background: var(--nominal); border-color: var(--nominal); color: #fff; }
      .reject { color: var(--limit); }

      .decided { font-size: 13.5px; margin: 12px 0 0; }
      .note-back { display: block; color: var(--muted); margin-top: 3px; }
      .error { color: var(--limit); font-size: 13px; }
    `,
  ],
})
export class AgentPanel {
  private api = inject(Api);
  private engineer = inject(Engineer);
  private destroyRef = inject(DestroyRef);

  readonly alarmId = input.required<number>();

  protected readonly ACTION_LABEL = ACTION_LABEL;
  protected readonly run = signal<AgentRun | null>(null);
  protected readonly steps = signal<AgentStep[]>([]);
  protected readonly busy = signal(false);
  protected readonly error = signal<string | null>(null);

  protected note = '';
  protected editAction: Action = 'escalate';

  private timer: ReturnType<typeof setTimeout> | null = null;

  constructor() {
    this.destroyRef.onDestroy(() => this.stopPolling());
    // Pick up an investigation that already exists for this alarm.
    queueMicrotask(() => {
      this.api
        .runsForAlarm(this.alarmId())
        .pipe(takeUntilDestroyed(this.destroyRef))
        .subscribe((runs) => {
          if (runs.length) {
            this.run.set(runs[0]);
            this.refresh(runs[0].id);
          }
        });
    });
  }

  protected start(): void {
    this.busy.set(true);
    this.error.set(null);
    this.api.startTriage(this.alarmId()).subscribe({
      next: (started) => {
        this.busy.set(false);
        this.refresh(started.agent_run_id);
      },
      error: (err) => {
        this.busy.set(false);
        this.error.set(this.message(err, 'Could not start the investigation.'));
      },
    });
  }

  protected decide(decision: ReviewDecision): void {
    const run = this.run();
    if (!run) return;
    this.busy.set(true);
    this.error.set(null);
    this.api
      .review(run.id, {
        decision,
        engineer: this.engineer.name(),
        final_action: decision === 'edit' ? this.editAction : null,
        note: this.note,
      })
      .subscribe({
        next: (updated) => {
          this.busy.set(false);
          this.note = '';
          this.run.set(updated);
          this.refresh(updated.id);
        },
        error: (err) => {
          this.busy.set(false);
          this.error.set(this.message(err, 'Could not record the decision.'));
        },
      });
  }

  /** Poll while the agent is working. Stops as soon as it needs a human or finishes. */
  private refresh(runId: number): void {
    this.api.run(runId).subscribe({
      next: (run) => {
        this.run.set(run);
        this.api.trace(runId).subscribe((steps) => this.steps.set(steps));
        if (run.status === 'running') {
          this.timer = setTimeout(() => this.refresh(runId), POLL_MS);
        } else {
          this.stopPolling();
        }
      },
      error: () => this.stopPolling(),
    });
  }

  private stopPolling(): void {
    if (this.timer) clearTimeout(this.timer);
    this.timer = null;
  }

  protected statusLabel(run: AgentRun): string {
    switch (run.status) {
      case 'running':
        return 'Investigating…';
      case 'awaiting_review':
        return 'Waiting for your decision';
      case 'completed':
        return `Closed · ${run.model}`;
      case 'failed':
        return 'The investigation failed';
    }
  }

  protected decidedLabel(status: string): string {
    return status === 'approved' ? 'Approved' : status === 'edited' ? 'Edited' : 'Rejected';
  }

  protected compact(args: Record<string, unknown>): string {
    return Object.entries(args)
      .map(([k, v]) => `${k}=${v}`)
      .join(' ');
  }

  private message(err: unknown, fallback: string): string {
    const detail = (err as { error?: { detail?: string } })?.error?.detail;
    return detail ?? fallback;
  }
}
