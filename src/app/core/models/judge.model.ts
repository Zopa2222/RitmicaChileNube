// Judge role types (scoring roles)
export type JudgeRole = 'DA' | 'DB' | 'E' | 'A' | 'L' | 'P';

// Judge registered per banca (setup/configuration)
export interface BancaJudge {
    name: string;
    roleAM: JudgeRole | null;  // null = no trabaja en AM
    rolePM: JudgeRole | null;  // null = no trabaja en PM
}

// Judge resolved for scoring (runtime) — used by ScoringService
export interface Judge {
    name: string;
    role: JudgeRole;
    index?: number; // For E1, E2, E3, E4 or A1, A2, A3, A4
}

// Get display name for judge (e.g., "DA", "E1", "A2")
export function getJudgeDisplayName(judge: Judge): string {
    if (judge.role === 'DA' || judge.role === 'DB' || judge.role === 'L' || judge.role === 'P') {
        return judge.role;
    }
    return `${judge.role}${judge.index || 1}`;
}

// Resolve BancaJudge[] for a given jornada into Judge[] for scoring
// Filters out L and P roles (no score columns), assigns indexes
export function resolveJudgesForScoring(bancaJudges: BancaJudge[], jornada: 'AM' | 'PM'): Judge[] {
    const judges: Judge[] = [];
    const roleCounters: { [key: string]: number } = {};

    for (const bj of bancaJudges) {
        const role = jornada === 'AM' ? bj.roleAM : bj.rolePM;
        if (!role) continue;           // no trabaja en esta jornada
        if (role === 'L' || role === 'P') continue;  // no generan columna

        const judge: Judge = { name: bj.name, role };

        if (role === 'E' || role === 'A') {
            roleCounters[role] = (roleCounters[role] || 0) + 1;
            judge.index = roleCounters[role];
        }

        judges.push(judge);
    }

    return judges;
}
