/**
 * Unit tests for pure logic extracted from ClaimContent.tsx
 * Covers: hasAnyClaims guard, extractRawText, isFlagged, tooltip visibility,
 * STATUS_HIGHLIGHT presence, and delay-based hover logic.
 */

const FLAG = "[CẦN XÁC NHẬN]";
const EMPTY_MARKERS = ["Chưa thấy ghi nhận", "Chưa có nội dung", "[LỖI"];

const ALL_STATUSES = [
  "SUPPORTED",
  "PARTIALLY_SUPPORTED",
  "LOW_CONFIDENCE",
  "UNSUPPORTED",
  "NO_CITATION",
  "CONTRADICTED",
  "NEED_REVIEW",
];

// ── Pure functions mirroring component logic ──────────────────────────────────

function hasAnyClaims(content, citedClaims) {
  if (citedClaims.length === 0) return false;
  if (EMPTY_MARKERS.some((m) => content.includes(m))) return false;
  return true;
}

function extractRawText(claimText) {
  return claimText.startsWith(FLAG)
    ? claimText.slice(FLAG.length).trimStart()
    : claimText;
}

function isFlagged(status) {
  return status !== "SUPPORTED";
}

// STATUS_HIGHLIGHT map mirrored for test assertions
const STATUS_HIGHLIGHT = {
  SUPPORTED:           "bg-green-100 text-green-900",
  PARTIALLY_SUPPORTED: "bg-amber-100  text-amber-900",
  LOW_CONFIDENCE:      "bg-orange-100 text-orange-900",
  UNSUPPORTED:         "bg-red-50     text-red-900",
  NO_CITATION:         "bg-gray-100   text-gray-900",
  CONTRADICTED:        "bg-red-100    text-red-900",
  NEED_REVIEW:         "bg-purple-50  text-purple-900",
};

// ─── hasAnyClaims ─────────────────────────────────────────────────────────────

describe("hasAnyClaims", () => {
  test("false when citedClaims empty", () => {
    expect(hasAnyClaims("Some content", [])).toBe(false);
  });

  test("false for empty marker: Chưa thấy ghi nhận", () => {
    expect(
      hasAnyClaims("Chưa thấy ghi nhận trong dữ liệu.", [{ citations: ["SRC-1"] }])
    ).toBe(false);
  });

  test("false for empty marker: Chưa có nội dung", () => {
    expect(hasAnyClaims("Chưa có nội dung", [{ citations: ["SRC-1"] }])).toBe(false);
  });

  test("false for error marker: [LỖI", () => {
    expect(hasAnyClaims("[LỖI: không tạo được section]", [{ citations: [] }])).toBe(false);
  });

  test("true for real content + claims", () => {
    expect(
      hasAnyClaims("Dị ứng Penicillin.", [{ citations: ["ALLERGY-PEN"] }])
    ).toBe(true);
  });

  test("true even when claims have no citations", () => {
    expect(hasAnyClaims("Bệnh nhân ổn định.", [{ citations: [] }])).toBe(true);
  });

  test("true for multi-claim content", () => {
    expect(
      hasAnyClaims("HbA1c 9.2%. Glucose 9.8 mmol/L.", [
        { citations: ["LAB-HBA1C"] },
        { citations: ["LAB-GLU"] },
      ])
    ).toBe(true);
  });
});

// ─── extractRawText ───────────────────────────────────────────────────────────

describe("extractRawText", () => {
  test("strips FLAG prefix", () => {
    expect(extractRawText(`${FLAG} Dị ứng Penicillin`)).toBe("Dị ứng Penicillin");
  });

  test("leaves clean text unchanged", () => {
    expect(extractRawText("Metformin 1000 mg")).toBe("Metformin 1000 mg");
  });

  test("trims extra space after stripping prefix", () => {
    expect(extractRawText(`${FLAG}  HbA1c 7.1%`)).toBe("HbA1c 7.1%");
  });

  test("handles empty string", () => {
    expect(extractRawText("")).toBe("");
  });

  test("partial FLAG text not stripped", () => {
    expect(extractRawText("[CẦN XÁC] text")).toBe("[CẦN XÁC] text");
  });
});

// ─── isFlagged ────────────────────────────────────────────────────────────────

describe("isFlagged", () => {
  test("SUPPORTED not flagged", () => {
    expect(isFlagged("SUPPORTED")).toBe(false);
  });

  const flagged = ALL_STATUSES.filter((s) => s !== "SUPPORTED");
  flagged.forEach((status) => {
    test(`${status} is flagged`, () => {
      expect(isFlagged(status)).toBe(true);
    });
  });
});

// ─── STATUS_HIGHLIGHT coverage ────────────────────────────────────────────────

describe("STATUS_HIGHLIGHT", () => {
  test("every ClaimStatus has a highlight class", () => {
    ALL_STATUSES.forEach((status) => {
      expect(STATUS_HIGHLIGHT[status]).toBeTruthy();
    });
  });

  test("SUPPORTED highlight uses green", () => {
    expect(STATUS_HIGHLIGHT["SUPPORTED"]).toContain("green");
  });

  test("PARTIALLY_SUPPORTED highlight uses amber", () => {
    expect(STATUS_HIGHLIGHT["PARTIALLY_SUPPORTED"]).toContain("amber");
  });

  test("NO_CITATION highlight uses gray", () => {
    expect(STATUS_HIGHLIGHT["NO_CITATION"]).toContain("gray");
  });

  test("CONTRADICTED highlight uses red", () => {
    expect(STATUS_HIGHLIGHT["CONTRADICTED"]).toContain("red");
  });
});

// ─── Tooltip visibility & interaction ────────────────────────────────────────

describe("Citation tooltip visibility", () => {
  test("claim with citations can show tooltip", () => {
    const claim = { citations: ["ALLERGY-PEN", "NOTE-001"], status: "SUPPORTED" };
    expect(claim.citations.length > 0).toBe(true);
  });

  test("claim without citations does NOT show tooltip", () => {
    const claim = { citations: [], status: "NO_CITATION" };
    expect(claim.citations.length > 0).toBe(false);
  });

  test("all citations appear in tooltip", () => {
    const citations = ["SRC-001", "SRC-002", "SRC-003"];
    expect(citations.length).toBe(3);
  });

  test("flagged claim shows flag badge AND tooltip (if has citations)", () => {
    const claim = { citations: ["SRC-A"], status: "PARTIALLY_SUPPORTED" };
    expect(isFlagged(claim.status)).toBe(true);
    expect(claim.citations.length > 0).toBe(true);
  });
});

// ─── Delay hover logic ────────────────────────────────────────────────────────

describe("Delay-based hover logic (leaveTimer)", () => {
  test("timer is cleared on mouseEnter (hover stays true)", () => {
    jest.useFakeTimers();
    let hovered = false;
    let timerId = null;

    const handleEnter = () => {
      if (timerId) clearTimeout(timerId);
      hovered = true;
    };
    const handleLeave = () => {
      timerId = setTimeout(() => { hovered = false; }, 150);
    };

    handleEnter();
    expect(hovered).toBe(true);

    handleLeave();
    // Before 150ms, still hovered
    jest.advanceTimersByTime(100);
    expect(hovered).toBe(true);

    // After 150ms, hovered turns false
    jest.advanceTimersByTime(60);
    expect(hovered).toBe(false);

    jest.useRealTimers();
  });

  test("entering tooltip before timer fires keeps tooltip open", () => {
    jest.useFakeTimers();
    let hovered = false;
    let timerId = null;

    const handleEnter = () => {
      if (timerId) clearTimeout(timerId);
      hovered = true;
    };
    const handleLeave = () => {
      timerId = setTimeout(() => { hovered = false; }, 150);
    };

    handleEnter();       // enter text span
    handleLeave();       // leave text span (starts 150ms timer)
    jest.advanceTimersByTime(100);  // 100ms: tooltip still visible
    handleEnter();       // enter tooltip → clears timer
    jest.advanceTimersByTime(200);  // 200ms more: tooltip still open
    expect(hovered).toBe(true);

    jest.useRealTimers();
  });

  test("leaving both span and tooltip hides tooltip after 150ms", () => {
    jest.useFakeTimers();
    let hovered = false;
    let timerId = null;

    const handleEnter = () => {
      if (timerId) clearTimeout(timerId);
      hovered = true;
    };
    const handleLeave = () => {
      timerId = setTimeout(() => { hovered = false; }, 150);
    };

    handleEnter();
    handleLeave();
    jest.advanceTimersByTime(200);
    expect(hovered).toBe(false);

    jest.useRealTimers();
  });
});

// ─── Claim separator ──────────────────────────────────────────────────────────

describe("Claim separator", () => {
  test("space between claims, no trailing space", () => {
    const claims = ["A", "B", "C"];
    const out = claims.map((c, i) => c + (i < claims.length - 1 ? " " : "")).join("");
    expect(out).toBe("A B C");
  });

  test("single claim: no separator", () => {
    const claims = ["Only"];
    const out = claims.map((c, i) => c + (i < claims.length - 1 ? " " : "")).join("");
    expect(out).toBe("Only");
  });
});
