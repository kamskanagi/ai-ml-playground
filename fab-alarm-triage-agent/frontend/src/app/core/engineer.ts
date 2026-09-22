import { Injectable, signal } from '@angular/core';

const STORAGE_KEY = 'fab-triage.engineer';

/** Who is signed in, for the decision log.
 *
 * There is no authentication here on purpose — the point of the project is the agent and
 * the review step, not identity. But every decision is attributed, so the audit log means
 * something, and the name persists across reloads.
 */
@Injectable({ providedIn: 'root' })
export class Engineer {
  static readonly ROSTER = [
    'R. Okafor',
    'L. Tanaka',
    'M. Silva',
    'A. Haddad',
    'J. Whitfield',
  ];

  private readonly current = signal<string>(this.restore());

  /** Read-only to callers; changes go through `choose`. */
  readonly name = this.current.asReadonly();

  /** Persist synchronously rather than through an effect.
   *
   * An effect flushes on the next change-detection pass, so a reload immediately after
   * picking a name could miss it. Writing here keeps the stored value and the signal in
   * step at all times.
   */
  choose(name: string): void {
    this.current.set(name);
    try {
      localStorage.setItem(STORAGE_KEY, name);
    } catch {
      // Private browsing or blocked storage. The picker still works for this session.
    }
  }

  private restore(): string {
    try {
      return localStorage.getItem(STORAGE_KEY) ?? Engineer.ROSTER[0];
    } catch {
      return Engineer.ROSTER[0];
    }
  }
}
