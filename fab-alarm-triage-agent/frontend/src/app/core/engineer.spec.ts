import { TestBed } from '@angular/core/testing';

import { Engineer } from './engineer';

describe('Engineer', () => {
  beforeEach(() => {
    localStorage.clear();
    TestBed.configureTestingModule({});
  });

  it('starts with someone selected so decisions are never unattributed', () => {
    const engineer = TestBed.inject(Engineer);
    expect(Engineer.ROSTER).toContain(engineer.name());
  });

  it('remembers the choice across reloads', () => {
    TestBed.inject(Engineer).choose('M. Silva');
    TestBed.resetTestingModule();
    TestBed.configureTestingModule({});
    expect(TestBed.inject(Engineer).name()).toBe('M. Silva');
  });

  it('writes the choice immediately, not on a later change-detection pass', () => {
    TestBed.inject(Engineer).choose('A. Haddad');
    expect(localStorage.getItem('fab-triage.engineer')).toBe('A. Haddad');
  });

  it('still works when storage is unavailable', () => {
    const getItem = Storage.prototype.getItem;
    Storage.prototype.getItem = () => {
      throw new Error('blocked');
    };
    try {
      expect(Engineer.ROSTER).toContain(TestBed.inject(Engineer).name());
    } finally {
      Storage.prototype.getItem = getItem;
    }
  });
});
