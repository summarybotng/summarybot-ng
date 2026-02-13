/**
 * Timezone Context for consistent date/time display across the app.
 * Stores the user's preferred timezone in localStorage.
 */

import { createContext, useContext, useState, useEffect, ReactNode } from "react";

// Common timezones grouped by region
export const TIMEZONE_OPTIONS = [
  // Americas
  { value: "America/New_York", label: "Eastern Time (ET)", group: "Americas" },
  { value: "America/Chicago", label: "Central Time (CT)", group: "Americas" },
  { value: "America/Denver", label: "Mountain Time (MT)", group: "Americas" },
  { value: "America/Los_Angeles", label: "Pacific Time (PT)", group: "Americas" },
  { value: "America/Anchorage", label: "Alaska Time (AKT)", group: "Americas" },
  { value: "America/Toronto", label: "Toronto (ET)", group: "Americas" },
  { value: "America/Vancouver", label: "Vancouver (PT)", group: "Americas" },
  { value: "America/Sao_Paulo", label: "São Paulo (BRT)", group: "Americas" },
  // Europe
  { value: "Europe/London", label: "London (GMT/BST)", group: "Europe" },
  { value: "Europe/Paris", label: "Paris (CET)", group: "Europe" },
  { value: "Europe/Berlin", label: "Berlin (CET)", group: "Europe" },
  { value: "Europe/Amsterdam", label: "Amsterdam (CET)", group: "Europe" },
  { value: "Europe/Moscow", label: "Moscow (MSK)", group: "Europe" },
  // Asia
  { value: "Asia/Dubai", label: "Dubai (GST)", group: "Asia" },
  { value: "Asia/Kolkata", label: "India (IST)", group: "Asia" },
  { value: "Asia/Singapore", label: "Singapore (SGT)", group: "Asia" },
  { value: "Asia/Hong_Kong", label: "Hong Kong (HKT)", group: "Asia" },
  { value: "Asia/Tokyo", label: "Tokyo (JST)", group: "Asia" },
  { value: "Asia/Shanghai", label: "Shanghai (CST)", group: "Asia" },
  { value: "Asia/Seoul", label: "Seoul (KST)", group: "Asia" },
  // Oceania
  { value: "Australia/Sydney", label: "Sydney (AEST)", group: "Oceania" },
  { value: "Australia/Melbourne", label: "Melbourne (AEST)", group: "Oceania" },
  { value: "Australia/Perth", label: "Perth (AWST)", group: "Oceania" },
  { value: "Pacific/Auckland", label: "Auckland (NZST)", group: "Oceania" },
  // UTC
  { value: "UTC", label: "UTC", group: "UTC" },
];

const STORAGE_KEY = "summarybot_timezone";

interface TimezoneContextType {
  timezone: string;
  setTimezone: (tz: string) => void;
  formatDate: (date: string | Date, options?: Intl.DateTimeFormatOptions) => string;
  formatTime: (date: string | Date, options?: Intl.DateTimeFormatOptions) => string;
  formatDateTime: (date: string | Date, options?: Intl.DateTimeFormatOptions) => string;
}

const TimezoneContext = createContext<TimezoneContextType | undefined>(undefined);

export function TimezoneProvider({ children }: { children: ReactNode }) {
  // Try to detect user's timezone, fall back to UTC
  const detectTimezone = () => {
    try {
      return Intl.DateTimeFormat().resolvedOptions().timeZone;
    } catch {
      return "UTC";
    }
  };

  const [timezone, setTimezoneState] = useState<string>(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    return stored || detectTimezone();
  });

  const setTimezone = (tz: string) => {
    setTimezoneState(tz);
    localStorage.setItem(STORAGE_KEY, tz);
  };

  // Ensure stored timezone is valid on mount
  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (!stored) {
      const detected = detectTimezone();
      localStorage.setItem(STORAGE_KEY, detected);
    }
  }, []);

  const formatDate = (date: string | Date, options?: Intl.DateTimeFormatOptions): string => {
    const d = typeof date === "string" ? new Date(date) : date;
    return d.toLocaleDateString(undefined, {
      timeZone: timezone,
      ...options,
    });
  };

  const formatTime = (date: string | Date, options?: Intl.DateTimeFormatOptions): string => {
    const d = typeof date === "string" ? new Date(date) : date;
    return d.toLocaleTimeString(undefined, {
      timeZone: timezone,
      hour: "2-digit",
      minute: "2-digit",
      ...options,
    });
  };

  const formatDateTime = (date: string | Date, options?: Intl.DateTimeFormatOptions): string => {
    const d = typeof date === "string" ? new Date(date) : date;
    return d.toLocaleString(undefined, {
      timeZone: timezone,
      ...options,
    });
  };

  return (
    <TimezoneContext.Provider
      value={{
        timezone,
        setTimezone,
        formatDate,
        formatTime,
        formatDateTime,
      }}
    >
      {children}
    </TimezoneContext.Provider>
  );
}

export function useTimezone() {
  const context = useContext(TimezoneContext);
  if (context === undefined) {
    throw new Error("useTimezone must be used within a TimezoneProvider");
  }
  return context;
}
