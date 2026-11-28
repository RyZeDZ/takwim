// Shapes returned by the backend (see backend/app/routes).

export interface Config {
  app_name: string
  days: string[]
  slots: string[]
  today: string
  week_start: string
  display_date: string // the week shown by default (next week once this one is over)
  today_is_working_day: boolean
  solver_seconds?: number
}

export interface GroupNode {
  id: number
  name: string
  kind: 'section' | 'td' | 'tp'
  size: number
  children: GroupNode[]
}

export interface LevelGroups {
  level: string
  sections: GroupNode[]
}

export type EntryKind = 'lecture' | 'td' | 'tp' | 'extra'

export interface WeekEntry {
  date: string
  day: number
  slot: number
  time: string
  module: string
  kind: EntryKind
  group: string
  group_id: number
  professor: string
  room: string
  session_id?: number
  claim_id?: number
  status: 'normal' | 'cancelled' | 'new'
}

export interface Week {
  week_start: string
  days: string[]
  slots: string[]
  dates: string[]
  entries: WeekEntry[]
}

export interface Room {
  id: number
  name: string
  type: 'amphi' | 'td' | 'lab'
  capacity: number
  active: boolean
}

export interface Level {
  id: number
  name: string
  headcount: number
}

export interface Module {
  id: number
  level_id: number
  name: string
  lecture_per_week: number
  td_per_week: number
  tp_per_week: number
}

export type Kind = 'lecture' | 'td' | 'tp'

export interface Teaching {
  module_id: number
  kinds: Kind[]
  rank: number
}

export interface Professor {
  id: number
  name: string
  max_sessions: number
  username: string | null
  teaches: Teaching[]
  availability_filled: boolean
}

export interface SlotRef {
  day: number
  slot: number
}

export interface Availability {
  unavailable: SlotRef[]
  avoid: SlotRef[]
}

export interface Credential {
  name: string
  username: string
  password: string
}

export interface Stats {
  rooms_active: number
  levels: number
  modules: number
  professors: number
  professors_with_availability: number
  sessions_per_week: number
  room_occupancy_percent: number
  absences: number
  upcoming_absences: number
  extra_sessions: number
  freed_rooms_reused: number
}

export interface Fix {
  code: 'no_teacher' | 'no_room_type' | 'room_too_small' | 'profs_full' | 'no_common_time'
  types?: string[]
  size?: number
  biggest?: number
  professors?: string[]
}

export interface Place {
  day: number
  slot: number
  room: string
  professor: string
}

export interface Change {
  module: string
  kind: string
  group: string
  from: Place
  to: Place
  reason: 'room_closed' | 'slot_removed' | 'prof_unavailable' | 'knock_on'
}

export interface GenerateResult {
  solver: string
  solver_stats?: { status: string; objective: number; best_bound: number; seconds: number } | null
  warning: string | null
  seconds: number
  groups_rebuilt_for: string[]
  requirements: number
  placed: number
  unscheduled: { requirement_id: string; reason: string; module: string; group: string; kind: string; fix?: Fix }[]
  changes?: Change[]
  conflicts: string[]
  sessions_moved: number | null
  gaps_per_group_per_week: number | null
  absences_kept: number
  absences_dropped: string[]
  claims_to_review: string[]
  saved: boolean
}

export interface Rules {
  week_days: string[]
  time_slots: string[]
  max_sessions_per_day_per_group: number
  max_sessions_per_day_per_professor: number
  max_sessions_in_a_row: number
  section_max_size: number
  td_group_size: number
  tp_group_size: number
  split_tp_groups: boolean
  default_max_sessions_per_professor: number
  room_types_for: Record<Kind, Room['type'][]>
}

export interface SettingsResponse {
  rules: Rules
  defaults: Rules
}

export interface SlotOption {
  date: string
  day: string
  slot: number
  time: string
  room: { id: number; name: string; type: string; capacity: number }
  freed_by_absence: boolean
  score: number
  reasons: string[]
}

export interface MyGroup {
  group_id: number
  group: string
  group_kind: string
  size: number
  module_id: number
  module: string
  kind: Kind
}

export interface Absence {
  id: number
  session_id: number
  date: string
  slot: number
  module: string
  group: string
  room_freed: string
}

export interface Claim {
  id: number
  date: string
  slot: number
  time: string
  group: string
  room: string
  module: string | null
  professor: string
}

export interface LogRow {
  at: string
  user: string
  action: string
  detail: string
}

export interface FreeRoom {
  id: number
  name: string
  type: string
  capacity: number
  freed_by_absence: boolean
}

export interface ImportField {
  required: boolean
  examples: string[]
}

export interface ImportPreview {
  kind: string
  filename: string
  columns: string[]
  mapping: Record<string, { column: string; confidence: number; method: string }>
  unmapped_columns: string[]
  missing_fields: string[]
  missing_required: string[]
  rows: Record<string, unknown>[]
  row_count: number
  warnings: string[]
  ready: boolean
}

export interface ImportResult {
  created: number
  updated: number
  skipped: number
  warnings: string[]
  credentials: Credential[]
}
