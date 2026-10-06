import { describe, expect, it } from 'vitest';
import { localDateTimeToUtc } from './admin-shared';

describe('campus-local scheduling', () => {
  it('converts a valid campus wall-clock time to an explicit UTC timestamp', () => {
    expect(localDateTimeToUtc('2026-01-15T09:30', 'America/New_York')).toBe('2026-01-15T14:30:00.000Z');
    expect(localDateTimeToUtc('2026-01-15T09:30', 'UTC')).toBe('2026-01-15T09:30:00.000Z');
  });

  it('rejects a nonexistent daylight-saving wall-clock time', () => {
    expect(() => localDateTimeToUtc('2026-03-08T02:30', 'America/New_York'))
      .toThrow(/daylight-saving transition/i);
  });

  it('requires both start/end fields to be selected', () => {
    expect(() => localDateTimeToUtc('', 'UTC')).toThrow(/Choose both/i);
  });
});
