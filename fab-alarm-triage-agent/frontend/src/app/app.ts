import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RouterLink, RouterOutlet } from '@angular/router';

import { Engineer } from './core/engineer';

@Component({
  selector: 'app-root',
  changeDetection: ChangeDetectionStrategy.OnPush,
  imports: [RouterOutlet, RouterLink, FormsModule],
  template: `
    <header class="bar">
      <a routerLink="/alarms" class="brand">
        <span class="mark"></span>
        Etch bay triage
      </a>
      <label class="who">
        Signed in as
        <select [ngModel]="engineer.name()" (ngModelChange)="engineer.choose($event)">
          @for (name of roster; track name) {
            <option [value]="name">{{ name }}</option>
          }
        </select>
      </label>
    </header>

    <main><router-outlet /></main>
  `,
  styles: [
    `
      .bar {
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 16px;
        padding: 14px var(--gutter);
        border-bottom: 1px solid var(--line);
        background: var(--surface);
      }
      .brand {
        display: flex;
        align-items: center;
        gap: 9px;
        font-family: var(--display);
        font-weight: 800;
        font-size: 15px;
        letter-spacing: -0.01em;
        text-decoration: none;
      }
      /* A chamber seen from above: the one piece of ornament, and it is the subject. */
      .mark {
        width: 13px;
        height: 13px;
        border: 2px solid var(--escalate);
        border-radius: 50%;
        box-shadow: inset 0 0 0 2px var(--surface), inset 0 0 0 4px var(--escalate);
      }
      .who { font-size: 12px; color: var(--muted); }
      select {
        font-family: inherit;
        font-size: 13px;
        color: var(--ink);
        background: var(--surface);
        border: 1px solid var(--line);
        border-radius: var(--radius);
        padding: 4px 6px;
        margin-left: 6px;
      }
      main { padding: 24px var(--gutter) 64px; max-width: 1240px; margin: 0 auto; }
    `,
  ],
})
export class App {
  protected readonly engineer = inject(Engineer);
  protected readonly roster = Engineer.ROSTER;
}
