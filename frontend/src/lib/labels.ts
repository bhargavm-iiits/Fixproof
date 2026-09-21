/**
 * Every technical term this project uses, in plain English, in one place.
 *
 * The backend's vocabulary is precise and stays precise. This file is the only
 * thing that decides how it is *said* to someone who does not write software,
 * so the two can never drift apart in three different components.
 */

export type Plain = { title: string; detail: string; technical?: string };

/** The nine checks, in the order they run. */
export const CHECKS: Plain[] = [
  {
    technical: "diff_parses",
    title: "The edit makes sense",
    detail:
      "An edit has to say exactly which lines it replaces. If the AI's answer is garbled, or claims to change more lines than it actually lists, we stop here.",
  },
  {
    technical: "scope",
    title: "It only touched the file it was allowed to",
    detail:
      "Each bug names one file that may be changed. Wandering into other files is refused, even if the change looks reasonable.",
  },
  {
    technical: "no_test_edits",
    title: "It didn't change the test",
    detail:
      "This is the one that matters most. A test describes what the code is supposed to do. Rewriting the test so it agrees with the broken code makes the failure disappear without fixing anything — so we refuse it, every time, and count how often it was tried.",
  },
  {
    technical: "no_new_or_deleted_files",
    title: "It didn't add, delete or rename files",
    detail:
      "A fix for one bug in one file has no business creating new files or removing old ones — including quietly, alongside a change that looks fine.",
  },
  {
    technical: "size",
    title: "The change is small enough",
    detail:
      "A one-line bug does not need a forty-line rewrite. A sprawling change is usually the AI guessing rather than fixing.",
  },
  {
    technical: "syntax",
    title: "The code still runs",
    detail: "The edited file has to be valid code. Cheap to check here, slow to discover later.",
  },
  {
    technical: "lint",
    title: "It didn't make the code messier",
    detail:
      "We compare against the broken version, not against perfection — so a good fix is never punished for untidiness it inherited.",
  },
  {
    technical: "no_new_imports",
    title: "It didn't pull in anything new",
    detail: "No new libraries. A fix should use what is already there.",
  },
  {
    technical: "no_dangerous_calls",
    title: "It didn't add anything dangerous",
    detail:
      "No running shell commands, opening network connections, or deleting files. Newly added only — whatever the file already did is not this fix's doing.",
  },
];

/** Not one of the nine, but it can reject an attempt, so it needs a plain name too. */
export const EXTRA_CHECKS: Plain[] = [
  {
    technical: "apply",
    title: "The edit could actually be applied",
    detail:
      "The AI described a change to lines that don't look the way it claimed, so there was nothing to apply it to. Usually it misremembered the file.",
  },
];

export const CHECK_BY_NAME = new Map(
  [...CHECKS, ...EXTRA_CHECKS].map((check) => [check.technical as string, check]),
);

export function checkLabel(name: string): Plain {
  return CHECK_BY_NAME.get(name) ?? { title: name.replace(/_/g, " "), detail: "", technical: name };
}

/** The seven things a run does, in order. */
export const STEPS: Plain[] = [
  {
    technical: "prepare",
    title: "Make a clean copy, then break it",
    detail: "We copy the program and introduce the bug, so every run starts from the same place.",
  },
  {
    technical: "baseline",
    title: "See exactly what's failing",
    detail:
      "Run the whole test suite before touching anything. Now we know which tests pass — so later we can tell if a fix broke one.",
  },
  {
    technical: "retrieve",
    title: "Gather the relevant code",
    detail: "Pull together the failing test and the file the AI is allowed to edit.",
  },
  {
    technical: "propose",
    title: "Ask the AI for fixes",
    detail: "Usually two or three attempts, each a different idea about what's wrong.",
  },
  {
    technical: "gate",
    title: "Run the nine checks",
    detail:
      "Fast, and they stop at the first failure. Every attempt rejected here is a sandbox we didn't have to start.",
  },
  {
    technical: "verify",
    title: "Actually run the tests, in a sandbox",
    detail:
      "In a locked box with no internet access, a memory limit and a hard time limit. This is the only step allowed to say a fix worked.",
  },
  {
    technical: "select",
    title: "Pick the smallest fix that worked",
    detail: "If more than one passed, the smallest change wins. The same input always picks the same winner.",
  },
];

export const STEP_BY_NAME = new Map(STEPS.map((step) => [step.technical as string, step]));

/** How a finished run is described. */
export const OUTCOMES: Record<string, { title: string; detail: string; tone: "good" | "bad" | "warn" }> = {
  FIX_VERIFIED: {
    title: "Fixed, and proven",
    detail: "The failing test passes now, and nothing that worked before is broken.",
    tone: "good",
  },
  NO_VERIFIED_FIX: {
    title: "Nothing worked",
    detail: "At least one attempt was tested, but none of them actually fixed the bug.",
    tone: "warn",
  },
  ALL_GATED: {
    title: "Every attempt was rejected",
    detail: "None of the AI's suggestions passed the checks, so none of them were worth testing.",
    tone: "warn",
  },
  TIMEOUT: { title: "Ran out of time", detail: "The run hit its time limit and stopped.", tone: "bad" },
  ERROR: { title: "Something went wrong", detail: "The run failed before it could finish.", tone: "bad" },
};

export function outcomeOf(decision: string | null, status: string) {
  if (decision && OUTCOMES[decision]) return OUTCOMES[decision];
  if (status === "running" || status === "queued") {
    return { title: "Working…", detail: "The run is in progress.", tone: "warn" as const };
  }
  return { title: status, detail: "", tone: "warn" as const };
}

/** What the AI's individual attempts are called on screen. */
export const ATTEMPT_STATUS = {
  verified: { title: "This one worked", tone: "good" as const },
  rejected: { title: "Rejected by a check", tone: "bad" as const },
  tested: { title: "Tested, didn't fix it", tone: "warn" as const },
  proposed: { title: "Not yet checked", tone: "warn" as const },
};

/** Bug categories, said plainly. */
export const CATEGORIES: Record<string, string> = {
  off_by_one: "Counting error",
  wrong_operator: "Wrong comparison",
  none_handling: "Empty value mishandled",
  boundary_condition: "Edge case",
  regex_greedy: "Pattern matches too much",
  mutable_default_arg: "State leaks between calls",
  sort_instability: "Sorted in the wrong order",
  dict_key_mismatch: "Names don't match up",
  float_rounding: "Rounding error",
  swallowed_exception: "Error silently ignored",
  early_return: "Stops too soon",
  inverted_condition: "Condition backwards",
};

export function categoryLabel(category: string) {
  return CATEGORIES[category] ?? category.replace(/_/g, " ");
}

export const DIFFICULTY: Record<string, string> = {
  easy: "Small fix",
  medium: "Medium fix",
  hard: "Bigger fix",
};
