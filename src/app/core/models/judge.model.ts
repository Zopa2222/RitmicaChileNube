// Judge role types
export type JudgeRole = 'DA' | 'DA2' | 'DB' | 'DB2' | 'E' | 'A' | 'L';

// Judge interface
export interface Judge {
    name: string;
    role: JudgeRole;
    index?: number; // For E1, E2, E3, E4 or A1, A2, A3, A4
}

// Get display name for judge (e.g., "DA", "E1", "A2")
export function getJudgeDisplayName(judge: Judge): string {
    if (judge.role === 'DA' || judge.role === 'DB' || judge.role === 'L') {
        return judge.role;
    }
    return `${judge.role}${judge.index || 1}`;
}
