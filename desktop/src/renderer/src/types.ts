export interface Daren {
  wxid: string
  nickname: string
  stage: string
  reason: string
  updated: string
  roomId?: string
  replied_msg_ids?: string[]
}

export interface Stats {
  total: number
  pending: number
  added: number
  sent: number
  im_sent: number
  failed: number
  by_stage: Record<string, number>
}

export type RunStatus = 'pending' | 'running' | 'finished' | 'failed' | 'stopped' | 'stopping'

export interface Run {
  id: number
  run_type: string
  stage: string
  limit: number | null
  status: RunStatus
  exit_code: number | null
  started_at: string
  finished_at: string | null
  summary: string
}

export interface LogEntry {
  id: number
  run_id: number
  ts: string
  level: string
  message: string
}

export interface Settings {
  stage: string
  limit: number
  max_pages: number
  cat: string
  contacts: string
  text: string
}

export type AgentStatusName = 'wechat' | 'shop' | 'rag'
export type AgentState = 'stopped' | 'starting' | 'running' | 'degraded' | 'error'

export interface AgentStatus {
  name: AgentStatusName
  status: AgentState
  pid: number | null
  port: number | null
  detail: string
  last_health: string
  updated: string
}

export interface Preflight {
  wechat: boolean
  wxshop: boolean
  rag: boolean
}

export interface FilePayload {
  name: string
  count: number
  text: string
}

export interface FollowupRow {
  达人昵称?: string
  微信号?: string
  手机号?: string
  跟进状态?: string
  备注原因?: string
  达人评分?: number | null
  带货销售额?: string
  粉丝数?: string
  采集时间?: string
  登记时间?: string
  来源页面?: string
  达人等级?: string
}

export interface FollowupData {
  total: number
  shown: number
  rows: FollowupRow[]
  stats: Record<string, number>
}
