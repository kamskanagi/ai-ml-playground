import { Routes } from '@angular/router';

export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'alarms' },
  {
    path: 'alarms',
    loadComponent: () => import('./features/queue/queue').then((m) => m.Queue),
  },
  {
    path: 'alarms/:id',
    // `withComponentInputBinding` maps the :id segment onto the component's input.
    loadComponent: () => import('./features/detail/detail').then((m) => m.Detail),
  },
  {
    path: 'metrics',
    loadComponent: () => import('./features/metrics/metrics').then((m) => m.MetricsPage),
  },
  { path: '**', redirectTo: 'alarms' },
];
