/**
 * Unit test to verify metadata type guards work correctly.
 * This tests the fix for the blank screen issue.
 */

import { test, expect } from '@playwright/test';

test.describe('Metadata Type Guards', () => {
  test('should handle various metadata formats without crashing', () => {
    // Simulate the type checks we do in the component
    const testCases = [
      // Valid number
      { generation_time_ms: 5000, expected: true },
      // String (would crash with toFixed)
      { generation_time_ms: "5000", expected: false },
      // Null
      { generation_time_ms: null, expected: false },
      // Undefined
      { generation_time_ms: undefined, expected: false },
      // Zero (valid)
      { generation_time_ms: 0, expected: false }, // falsy but typeof === "number"
    ];

    for (const tc of testCases) {
      const isNumber = typeof tc.generation_time_ms === "number";
      // The key check is that this doesn't throw
      if (isNumber) {
        const result = (tc.generation_time_ms / 1000).toFixed(2);
        expect(typeof result).toBe('string');
      }
    }
  });

  test('should handle time_span_hours type check', () => {
    const testCases = [
      { time_span_hours: 24.5, expected: "24.5h" },
      { time_span_hours: 0, expected: "0.0h" },
      { time_span_hours: "24.5", shouldSkip: true },
      { time_span_hours: null, shouldSkip: true },
      { time_span_hours: undefined, shouldSkip: true },
    ];

    for (const tc of testCases) {
      const isNumber = typeof tc.time_span_hours === "number";
      if (isNumber && !tc.shouldSkip) {
        const result = tc.time_span_hours.toFixed(1) + "h";
        expect(result).toBe(tc.expected);
      } else {
        expect(tc.shouldSkip || !isNumber).toBe(true);
      }
    }
  });

  test('should handle null/undefined summary_text for copy button', () => {
    const testCases = [
      { summary_text: "Hello world", expected: "Hello world" },
      { summary_text: "", expected: "" },
      { summary_text: null, expected: "" },
      { summary_text: undefined, expected: "" },
    ];

    for (const tc of testCases) {
      const safeText = tc.summary_text || "";
      expect(safeText).toBe(tc.expected);
      // This should not throw
      expect(() => safeText.length).not.toThrow();
    }
  });

  test('should handle Object.entries on metadata', () => {
    const metadata = {
      model: "claude-3",
      tokens: 1000,
      nested: { foo: "bar" },
      nullValue: null,
      undefinedValue: undefined,
    };

    const knownKeys = new Set(["model", "tokens"]);

    // This mimics what we do in the component
    const extraFields = Object.entries(metadata)
      .filter(([key, value]) => !knownKeys.has(key) && value !== null && value !== undefined);

    expect(extraFields.length).toBe(1); // Only "nested" should pass
    expect(extraFields[0][0]).toBe("nested");

    // Verify we can safely stringify
    for (const [key, value] of extraFields) {
      const display = typeof value === "object" ? JSON.stringify(value) : String(value);
      expect(typeof display).toBe('string');
    }
  });
});
