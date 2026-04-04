// Test file to debug FilterCriteriaSummary
import { format, parse } from "date-fns";
import type { SummaryFilterCriteria } from "@/types/filters";

// Simulate the criteria that comes from API after conversion
const testCriteria: SummaryFilterCriteria = {
  source: "scheduled",
  archived: false,
  archivePeriod: "2025-01-15",
  summaryLength: "detailed",
  perspective: "developer",
};

// Test the parse/format logic
function testParsing() {
  console.log("Testing archivePeriod parsing...");
  
  if (testCriteria.archivePeriod) {
    console.log("archivePeriod value:", testCriteria.archivePeriod);
    console.log("typeof archivePeriod:", typeof testCriteria.archivePeriod);
    
    try {
      const parsed = parse(testCriteria.archivePeriod, "yyyy-MM-dd", new Date());
      console.log("Parsed date:", parsed);
      
      const formatted = format(parsed, "MMM d, yyyy");
      console.log("Formatted:", formatted);
    } catch (e) {
      console.error("Parse error:", e);
    }
  }
}

testParsing();
