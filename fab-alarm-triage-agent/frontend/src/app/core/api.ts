import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import {
  Alarm,
  AgentRun,
  AgentStep,
  AlarmDetail,
  Metrics,
  ReviewRequest,
  SignalTrace,
  TriageStarted,
} from './models';

/** Every backend call the dashboard makes. */
@Injectable({ providedIn: 'root' })
export class Api {
  private http = inject(HttpClient);
  private base = '/api';

  alarms(status?: string): Observable<Alarm[]> {
    const query = status ? `?status=${status}&limit=200` : '?limit=200';
    return this.http.get<Alarm[]>(`${this.base}/alarms${query}`);
  }

  alarm(id: number): Observable<AlarmDetail> {
    return this.http.get<AlarmDetail>(`${this.base}/alarms/${id}`);
  }

  sensors(runId: number): Observable<{ signals: SignalTrace[] }> {
    return this.http.get<{ signals: SignalTrace[] }>(`${this.base}/runs/${runId}/sensors`);
  }

  runsForAlarm(alarmId: number): Observable<AgentRun[]> {
    return this.http.get<AgentRun[]>(`${this.base}/alarms/${alarmId}/agent-runs`);
  }

  startTriage(alarmId: number): Observable<TriageStarted> {
    return this.http.post<TriageStarted>(`${this.base}/alarms/${alarmId}/triage`, {});
  }

  run(runId: number): Observable<AgentRun> {
    return this.http.get<AgentRun>(`${this.base}/agent-runs/${runId}`);
  }

  trace(runId: number): Observable<AgentStep[]> {
    return this.http.get<AgentStep[]>(`${this.base}/agent-runs/${runId}/trace`);
  }

  metrics(): Observable<Metrics> {
    return this.http.get<Metrics>(`${this.base}/metrics/eval`);
  }

  review(runId: number, body: ReviewRequest): Observable<AgentRun> {
    return this.http.post<AgentRun>(`${this.base}/agent-runs/${runId}/review`, body);
  }
}
