
export type Json = string | number | boolean | null | { [key: string]: Json | undefined } | Json[]

export type Database = {

  "doctor": {
          Tables: {
            "agents": {
                  Row: {
                    "cert_fingerprint": string | null,"config": NonNullable<Json>,"config_version": number,"created_at": string,"created_by": string | null,"id": string,"integration_id": string,"last_seen_at": string | null,"name": string,"public_key": string | null,"registered_at": string | null,"registration_expires_at": string | null,"registration_token_hash": string | null,"revoked_at": string | null,"secret_hash": string | null,"status": string,"tenant_id": string,"updated_at": string,"version": string | null
                  }
                  ComputedFields: never
                  Insert: {
                    "cert_fingerprint"?: string | null,"config"?: NonNullable<Json>,"config_version"?: number,"created_at"?: string,"created_by"?: string | null,"id"?: string,"integration_id": string,"last_seen_at"?: string | null,"name": string,"public_key"?: string | null,"registered_at"?: string | null,"registration_expires_at"?: string | null,"registration_token_hash"?: string | null,"revoked_at"?: string | null,"secret_hash"?: string | null,"status"?: string,"tenant_id": string,"updated_at"?: string,"version"?: string | null
                  }
                  Update: {
                    "cert_fingerprint"?: string | null,"config"?: NonNullable<Json>,"config_version"?: number,"created_at"?: string,"created_by"?: string | null,"id"?: string,"integration_id"?: string,"last_seen_at"?: string | null,"name"?: string,"public_key"?: string | null,"registered_at"?: string | null,"registration_expires_at"?: string | null,"registration_token_hash"?: string | null,"revoked_at"?: string | null,"secret_hash"?: string | null,"status"?: string,"tenant_id"?: string,"updated_at"?: string,"version"?: string | null
                  }
                  Relationships: [
                    {
      foreignKeyName: "agents_tenant_id_fkey"
      columns: ["tenant_id"]
isOneToOne: false
      referencedRelation: "tenants"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "agents_tenant_id_integration_id_fkey"
      columns: ["tenant_id","integration_id"]
isOneToOne: false
      referencedRelation: "integrations"
      referencedColumns: ["tenant_id","id"]
    }
                  ]
                },"ai_profile_checks": {
                  Row: {
                    "checked_at": string,"detail": string | null,"hosts": (string)[],"id": number,"in_region": boolean,"ok": boolean,"profile": string,"region": string | null,"target": string
                  }
                  ComputedFields: never
                  Insert: {
                    "checked_at"?: string,"detail"?: string | null,"hosts"?: (string)[],"id"?: never,"in_region"?: boolean,"ok": boolean,"profile": string,"region"?: string | null,"target"?: string
                  }
                  Update: {
                    "checked_at"?: string,"detail"?: string | null,"hosts"?: (string)[],"id"?: never,"in_region"?: boolean,"ok"?: boolean,"profile"?: string,"region"?: string | null,"target"?: string
                  }
                  Relationships: [

                  ]
                },"alert_preferences": {
                  Row: {
                    "created_at": string,"id": string,"quiet_hours": Json | null,"tenant_id": string,"updated_at": string,"user_id": string
                  }
                  ComputedFields: never
                  Insert: {
                    "created_at"?: string,"id"?: string,"quiet_hours"?: Json | null,"tenant_id"?: string,"updated_at"?: string,"user_id"?: string
                  }
                  Update: {
                    "created_at"?: string,"id"?: string,"quiet_hours"?: Json | null,"tenant_id"?: string,"updated_at"?: string,"user_id"?: string
                  }
                  Relationships: [
                    {
      foreignKeyName: "alert_preferences_tenant_id_fkey"
      columns: ["tenant_id"]
isOneToOne: false
      referencedRelation: "tenants"
      referencedColumns: ["id"]
    }
                  ]
                },"alert_rules": {
                  Row: {
                    "channels": NonNullable<Json>,"conditions": NonNullable<Json>,"created_at": string,"created_by": string | null,"enabled": boolean,"id": string,"name": string,"quiet_hours": Json | null,"tenant_id": string,"updated_at": string
                  }
                  ComputedFields: never
                  Insert: {
                    "channels"?: NonNullable<Json>,"conditions": NonNullable<Json>,"created_at"?: string,"created_by"?: string | null,"enabled"?: boolean,"id"?: string,"name": string,"quiet_hours"?: Json | null,"tenant_id"?: string,"updated_at"?: string
                  }
                  Update: {
                    "channels"?: NonNullable<Json>,"conditions"?: NonNullable<Json>,"created_at"?: string,"created_by"?: string | null,"enabled"?: boolean,"id"?: string,"name"?: string,"quiet_hours"?: Json | null,"tenant_id"?: string,"updated_at"?: string
                  }
                  Relationships: [
                    {
      foreignKeyName: "alert_rules_tenant_id_fkey"
      columns: ["tenant_id"]
isOneToOne: false
      referencedRelation: "tenants"
      referencedColumns: ["id"]
    }
                  ]
                },"audit_logs": {
                  Row: {
                    "action": string,"actor_id": string | null,"actor_type": string,"after": Json | null,"before": Json | null,"id": number,"ip": unknown,"occurred_at": string,"request_id": string | null,"resource_id": string | null,"resource_type": string | null,"tenant_id": string,"user_agent": string | null
                  }
                  ComputedFields: never
                  Insert: {
                    "action": string,"actor_id"?: string | null,"actor_type": string,"after"?: Json | null,"before"?: Json | null,"id"?: number,"ip"?: unknown,"occurred_at"?: string,"request_id"?: string | null,"resource_id"?: string | null,"resource_type"?: string | null,"tenant_id": string,"user_agent"?: string | null
                  }
                  Update: {
                    "action"?: string,"actor_id"?: string | null,"actor_type"?: string,"after"?: Json | null,"before"?: Json | null,"id"?: number,"ip"?: unknown,"occurred_at"?: string,"request_id"?: string | null,"resource_id"?: string | null,"resource_type"?: string | null,"tenant_id"?: string,"user_agent"?: string | null
                  }
                  Relationships: [
                    {
      foreignKeyName: "audit_logs_tenant_id_fkey1"
      columns: ["tenant_id"]
isOneToOne: false
      referencedRelation: "tenants"
      referencedColumns: ["id"]
    }
                  ]
                },"audit_logs_2026_10": {
                  Row: {
                    "action": string,"actor_id": string | null,"actor_type": string,"after": Json | null,"before": Json | null,"id": number,"ip": unknown,"occurred_at": string,"request_id": string | null,"resource_id": string | null,"resource_type": string | null,"tenant_id": string,"user_agent": string | null
                  }
                  ComputedFields: never
                  Insert: {
                    "action": string,"actor_id"?: string | null,"actor_type": string,"after"?: Json | null,"before"?: Json | null,"id"?: number,"ip"?: unknown,"occurred_at"?: string,"request_id"?: string | null,"resource_id"?: string | null,"resource_type"?: string | null,"tenant_id": string,"user_agent"?: string | null
                  }
                  Update: {
                    "action"?: string,"actor_id"?: string | null,"actor_type"?: string,"after"?: Json | null,"before"?: Json | null,"id"?: number,"ip"?: unknown,"occurred_at"?: string,"request_id"?: string | null,"resource_id"?: string | null,"resource_type"?: string | null,"tenant_id"?: string,"user_agent"?: string | null
                  }
                  Relationships: [

                  ]
                },"audit_logs_2026_11": {
                  Row: {
                    "action": string,"actor_id": string | null,"actor_type": string,"after": Json | null,"before": Json | null,"id": number,"ip": unknown,"occurred_at": string,"request_id": string | null,"resource_id": string | null,"resource_type": string | null,"tenant_id": string,"user_agent": string | null
                  }
                  ComputedFields: never
                  Insert: {
                    "action": string,"actor_id"?: string | null,"actor_type": string,"after"?: Json | null,"before"?: Json | null,"id"?: number,"ip"?: unknown,"occurred_at"?: string,"request_id"?: string | null,"resource_id"?: string | null,"resource_type"?: string | null,"tenant_id": string,"user_agent"?: string | null
                  }
                  Update: {
                    "action"?: string,"actor_id"?: string | null,"actor_type"?: string,"after"?: Json | null,"before"?: Json | null,"id"?: number,"ip"?: unknown,"occurred_at"?: string,"request_id"?: string | null,"resource_id"?: string | null,"resource_type"?: string | null,"tenant_id"?: string,"user_agent"?: string | null
                  }
                  Relationships: [

                  ]
                },"audit_logs_2026_12": {
                  Row: {
                    "action": string,"actor_id": string | null,"actor_type": string,"after": Json | null,"before": Json | null,"id": number,"ip": unknown,"occurred_at": string,"request_id": string | null,"resource_id": string | null,"resource_type": string | null,"tenant_id": string,"user_agent": string | null
                  }
                  ComputedFields: never
                  Insert: {
                    "action": string,"actor_id"?: string | null,"actor_type": string,"after"?: Json | null,"before"?: Json | null,"id"?: number,"ip"?: unknown,"occurred_at"?: string,"request_id"?: string | null,"resource_id"?: string | null,"resource_type"?: string | null,"tenant_id": string,"user_agent"?: string | null
                  }
                  Update: {
                    "action"?: string,"actor_id"?: string | null,"actor_type"?: string,"after"?: Json | null,"before"?: Json | null,"id"?: number,"ip"?: unknown,"occurred_at"?: string,"request_id"?: string | null,"resource_id"?: string | null,"resource_type"?: string | null,"tenant_id"?: string,"user_agent"?: string | null
                  }
                  Relationships: [

                  ]
                },"audit_logs_2027_01": {
                  Row: {
                    "action": string,"actor_id": string | null,"actor_type": string,"after": Json | null,"before": Json | null,"id": number,"ip": unknown,"occurred_at": string,"request_id": string | null,"resource_id": string | null,"resource_type": string | null,"tenant_id": string,"user_agent": string | null
                  }
                  ComputedFields: never
                  Insert: {
                    "action": string,"actor_id"?: string | null,"actor_type": string,"after"?: Json | null,"before"?: Json | null,"id"?: number,"ip"?: unknown,"occurred_at"?: string,"request_id"?: string | null,"resource_id"?: string | null,"resource_type"?: string | null,"tenant_id": string,"user_agent"?: string | null
                  }
                  Update: {
                    "action"?: string,"actor_id"?: string | null,"actor_type"?: string,"after"?: Json | null,"before"?: Json | null,"id"?: number,"ip"?: unknown,"occurred_at"?: string,"request_id"?: string | null,"resource_id"?: string | null,"resource_type"?: string | null,"tenant_id"?: string,"user_agent"?: string | null
                  }
                  Relationships: [

                  ]
                },"audit_logs_2027_02": {
                  Row: {
                    "action": string,"actor_id": string | null,"actor_type": string,"after": Json | null,"before": Json | null,"id": number,"ip": unknown,"occurred_at": string,"request_id": string | null,"resource_id": string | null,"resource_type": string | null,"tenant_id": string,"user_agent": string | null
                  }
                  ComputedFields: never
                  Insert: {
                    "action": string,"actor_id"?: string | null,"actor_type": string,"after"?: Json | null,"before"?: Json | null,"id"?: number,"ip"?: unknown,"occurred_at"?: string,"request_id"?: string | null,"resource_id"?: string | null,"resource_type"?: string | null,"tenant_id": string,"user_agent"?: string | null
                  }
                  Update: {
                    "action"?: string,"actor_id"?: string | null,"actor_type"?: string,"after"?: Json | null,"before"?: Json | null,"id"?: number,"ip"?: unknown,"occurred_at"?: string,"request_id"?: string | null,"resource_id"?: string | null,"resource_type"?: string | null,"tenant_id"?: string,"user_agent"?: string | null
                  }
                  Relationships: [

                  ]
                },"audit_logs_2027_03": {
                  Row: {
                    "action": string,"actor_id": string | null,"actor_type": string,"after": Json | null,"before": Json | null,"id": number,"ip": unknown,"occurred_at": string,"request_id": string | null,"resource_id": string | null,"resource_type": string | null,"tenant_id": string,"user_agent": string | null
                  }
                  ComputedFields: never
                  Insert: {
                    "action": string,"actor_id"?: string | null,"actor_type": string,"after"?: Json | null,"before"?: Json | null,"id"?: number,"ip"?: unknown,"occurred_at"?: string,"request_id"?: string | null,"resource_id"?: string | null,"resource_type"?: string | null,"tenant_id": string,"user_agent"?: string | null
                  }
                  Update: {
                    "action"?: string,"actor_id"?: string | null,"actor_type"?: string,"after"?: Json | null,"before"?: Json | null,"id"?: number,"ip"?: unknown,"occurred_at"?: string,"request_id"?: string | null,"resource_id"?: string | null,"resource_type"?: string | null,"tenant_id"?: string,"user_agent"?: string | null
                  }
                  Relationships: [

                  ]
                },"audit_logs_2027_04": {
                  Row: {
                    "action": string,"actor_id": string | null,"actor_type": string,"after": Json | null,"before": Json | null,"id": number,"ip": unknown,"occurred_at": string,"request_id": string | null,"resource_id": string | null,"resource_type": string | null,"tenant_id": string,"user_agent": string | null
                  }
                  ComputedFields: never
                  Insert: {
                    "action": string,"actor_id"?: string | null,"actor_type": string,"after"?: Json | null,"before"?: Json | null,"id"?: number,"ip"?: unknown,"occurred_at"?: string,"request_id"?: string | null,"resource_id"?: string | null,"resource_type"?: string | null,"tenant_id": string,"user_agent"?: string | null
                  }
                  Update: {
                    "action"?: string,"actor_id"?: string | null,"actor_type"?: string,"after"?: Json | null,"before"?: Json | null,"id"?: number,"ip"?: unknown,"occurred_at"?: string,"request_id"?: string | null,"resource_id"?: string | null,"resource_type"?: string | null,"tenant_id"?: string,"user_agent"?: string | null
                  }
                  Relationships: [

                  ]
                },"audit_logs_2027_05": {
                  Row: {
                    "action": string,"actor_id": string | null,"actor_type": string,"after": Json | null,"before": Json | null,"id": number,"ip": unknown,"occurred_at": string,"request_id": string | null,"resource_id": string | null,"resource_type": string | null,"tenant_id": string,"user_agent": string | null
                  }
                  ComputedFields: never
                  Insert: {
                    "action": string,"actor_id"?: string | null,"actor_type": string,"after"?: Json | null,"before"?: Json | null,"id"?: number,"ip"?: unknown,"occurred_at"?: string,"request_id"?: string | null,"resource_id"?: string | null,"resource_type"?: string | null,"tenant_id": string,"user_agent"?: string | null
                  }
                  Update: {
                    "action"?: string,"actor_id"?: string | null,"actor_type"?: string,"after"?: Json | null,"before"?: Json | null,"id"?: number,"ip"?: unknown,"occurred_at"?: string,"request_id"?: string | null,"resource_id"?: string | null,"resource_type"?: string | null,"tenant_id"?: string,"user_agent"?: string | null
                  }
                  Relationships: [

                  ]
                },"audit_logs_2027_06": {
                  Row: {
                    "action": string,"actor_id": string | null,"actor_type": string,"after": Json | null,"before": Json | null,"id": number,"ip": unknown,"occurred_at": string,"request_id": string | null,"resource_id": string | null,"resource_type": string | null,"tenant_id": string,"user_agent": string | null
                  }
                  ComputedFields: never
                  Insert: {
                    "action": string,"actor_id"?: string | null,"actor_type": string,"after"?: Json | null,"before"?: Json | null,"id"?: number,"ip"?: unknown,"occurred_at"?: string,"request_id"?: string | null,"resource_id"?: string | null,"resource_type"?: string | null,"tenant_id": string,"user_agent"?: string | null
                  }
                  Update: {
                    "action"?: string,"actor_id"?: string | null,"actor_type"?: string,"after"?: Json | null,"before"?: Json | null,"id"?: number,"ip"?: unknown,"occurred_at"?: string,"request_id"?: string | null,"resource_id"?: string | null,"resource_type"?: string | null,"tenant_id"?: string,"user_agent"?: string | null
                  }
                  Relationships: [

                  ]
                },"audit_logs_2027_07": {
                  Row: {
                    "action": string,"actor_id": string | null,"actor_type": string,"after": Json | null,"before": Json | null,"id": number,"ip": unknown,"occurred_at": string,"request_id": string | null,"resource_id": string | null,"resource_type": string | null,"tenant_id": string,"user_agent": string | null
                  }
                  ComputedFields: never
                  Insert: {
                    "action": string,"actor_id"?: string | null,"actor_type": string,"after"?: Json | null,"before"?: Json | null,"id"?: number,"ip"?: unknown,"occurred_at"?: string,"request_id"?: string | null,"resource_id"?: string | null,"resource_type"?: string | null,"tenant_id": string,"user_agent"?: string | null
                  }
                  Update: {
                    "action"?: string,"actor_id"?: string | null,"actor_type"?: string,"after"?: Json | null,"before"?: Json | null,"id"?: number,"ip"?: unknown,"occurred_at"?: string,"request_id"?: string | null,"resource_id"?: string | null,"resource_type"?: string | null,"tenant_id"?: string,"user_agent"?: string | null
                  }
                  Relationships: [

                  ]
                },"audit_logs_2027_08": {
                  Row: {
                    "action": string,"actor_id": string | null,"actor_type": string,"after": Json | null,"before": Json | null,"id": number,"ip": unknown,"occurred_at": string,"request_id": string | null,"resource_id": string | null,"resource_type": string | null,"tenant_id": string,"user_agent": string | null
                  }
                  ComputedFields: never
                  Insert: {
                    "action": string,"actor_id"?: string | null,"actor_type": string,"after"?: Json | null,"before"?: Json | null,"id"?: number,"ip"?: unknown,"occurred_at"?: string,"request_id"?: string | null,"resource_id"?: string | null,"resource_type"?: string | null,"tenant_id": string,"user_agent"?: string | null
                  }
                  Update: {
                    "action"?: string,"actor_id"?: string | null,"actor_type"?: string,"after"?: Json | null,"before"?: Json | null,"id"?: number,"ip"?: unknown,"occurred_at"?: string,"request_id"?: string | null,"resource_id"?: string | null,"resource_type"?: string | null,"tenant_id"?: string,"user_agent"?: string | null
                  }
                  Relationships: [

                  ]
                },"audit_logs_2027_09": {
                  Row: {
                    "action": string,"actor_id": string | null,"actor_type": string,"after": Json | null,"before": Json | null,"id": number,"ip": unknown,"occurred_at": string,"request_id": string | null,"resource_id": string | null,"resource_type": string | null,"tenant_id": string,"user_agent": string | null
                  }
                  ComputedFields: never
                  Insert: {
                    "action": string,"actor_id"?: string | null,"actor_type": string,"after"?: Json | null,"before"?: Json | null,"id"?: number,"ip"?: unknown,"occurred_at"?: string,"request_id"?: string | null,"resource_id"?: string | null,"resource_type"?: string | null,"tenant_id": string,"user_agent"?: string | null
                  }
                  Update: {
                    "action"?: string,"actor_id"?: string | null,"actor_type"?: string,"after"?: Json | null,"before"?: Json | null,"id"?: number,"ip"?: unknown,"occurred_at"?: string,"request_id"?: string | null,"resource_id"?: string | null,"resource_type"?: string | null,"tenant_id"?: string,"user_agent"?: string | null
                  }
                  Relationships: [

                  ]
                },"audit_logs_2027_10": {
                  Row: {
                    "action": string,"actor_id": string | null,"actor_type": string,"after": Json | null,"before": Json | null,"id": number,"ip": unknown,"occurred_at": string,"request_id": string | null,"resource_id": string | null,"resource_type": string | null,"tenant_id": string,"user_agent": string | null
                  }
                  ComputedFields: never
                  Insert: {
                    "action": string,"actor_id"?: string | null,"actor_type": string,"after"?: Json | null,"before"?: Json | null,"id"?: number,"ip"?: unknown,"occurred_at"?: string,"request_id"?: string | null,"resource_id"?: string | null,"resource_type"?: string | null,"tenant_id": string,"user_agent"?: string | null
                  }
                  Update: {
                    "action"?: string,"actor_id"?: string | null,"actor_type"?: string,"after"?: Json | null,"before"?: Json | null,"id"?: number,"ip"?: unknown,"occurred_at"?: string,"request_id"?: string | null,"resource_id"?: string | null,"resource_type"?: string | null,"tenant_id"?: string,"user_agent"?: string | null
                  }
                  Relationships: [

                  ]
                },"audit_logs_2027_11": {
                  Row: {
                    "action": string,"actor_id": string | null,"actor_type": string,"after": Json | null,"before": Json | null,"id": number,"ip": unknown,"occurred_at": string,"request_id": string | null,"resource_id": string | null,"resource_type": string | null,"tenant_id": string,"user_agent": string | null
                  }
                  ComputedFields: never
                  Insert: {
                    "action": string,"actor_id"?: string | null,"actor_type": string,"after"?: Json | null,"before"?: Json | null,"id"?: number,"ip"?: unknown,"occurred_at"?: string,"request_id"?: string | null,"resource_id"?: string | null,"resource_type"?: string | null,"tenant_id": string,"user_agent"?: string | null
                  }
                  Update: {
                    "action"?: string,"actor_id"?: string | null,"actor_type"?: string,"after"?: Json | null,"before"?: Json | null,"id"?: number,"ip"?: unknown,"occurred_at"?: string,"request_id"?: string | null,"resource_id"?: string | null,"resource_type"?: string | null,"tenant_id"?: string,"user_agent"?: string | null
                  }
                  Relationships: [

                  ]
                },"audit_logs_2027_12": {
                  Row: {
                    "action": string,"actor_id": string | null,"actor_type": string,"after": Json | null,"before": Json | null,"id": number,"ip": unknown,"occurred_at": string,"request_id": string | null,"resource_id": string | null,"resource_type": string | null,"tenant_id": string,"user_agent": string | null
                  }
                  ComputedFields: never
                  Insert: {
                    "action": string,"actor_id"?: string | null,"actor_type": string,"after"?: Json | null,"before"?: Json | null,"id"?: number,"ip"?: unknown,"occurred_at"?: string,"request_id"?: string | null,"resource_id"?: string | null,"resource_type"?: string | null,"tenant_id": string,"user_agent"?: string | null
                  }
                  Update: {
                    "action"?: string,"actor_id"?: string | null,"actor_type"?: string,"after"?: Json | null,"before"?: Json | null,"id"?: number,"ip"?: unknown,"occurred_at"?: string,"request_id"?: string | null,"resource_id"?: string | null,"resource_type"?: string | null,"tenant_id"?: string,"user_agent"?: string | null
                  }
                  Relationships: [

                  ]
                },"audit_logs_default": {
                  Row: {
                    "action": string,"actor_id": string | null,"actor_type": string,"after": Json | null,"before": Json | null,"id": number,"ip": unknown,"occurred_at": string,"request_id": string | null,"resource_id": string | null,"resource_type": string | null,"tenant_id": string,"user_agent": string | null
                  }
                  ComputedFields: never
                  Insert: {
                    "action": string,"actor_id"?: string | null,"actor_type": string,"after"?: Json | null,"before"?: Json | null,"id"?: number,"ip"?: unknown,"occurred_at"?: string,"request_id"?: string | null,"resource_id"?: string | null,"resource_type"?: string | null,"tenant_id": string,"user_agent"?: string | null
                  }
                  Update: {
                    "action"?: string,"actor_id"?: string | null,"actor_type"?: string,"after"?: Json | null,"before"?: Json | null,"id"?: number,"ip"?: unknown,"occurred_at"?: string,"request_id"?: string | null,"resource_id"?: string | null,"resource_type"?: string | null,"tenant_id"?: string,"user_agent"?: string | null
                  }
                  Relationships: [

                  ]
                },"connector_syncs": {
                  Row: {
                    "checkpoint_from": Json | null,"checkpoint_to": Json | null,"connector_id": string,"error": string | null,"finished_at": string | null,"id": string,"records": number,"started_at": string,"status": string,"tenant_id": string
                  }
                  ComputedFields: never
                  Insert: {
                    "checkpoint_from"?: Json | null,"checkpoint_to"?: Json | null,"connector_id": string,"error"?: string | null,"finished_at"?: string | null,"id"?: string,"records"?: number,"started_at"?: string,"status"?: string,"tenant_id": string
                  }
                  Update: {
                    "checkpoint_from"?: Json | null,"checkpoint_to"?: Json | null,"connector_id"?: string,"error"?: string | null,"finished_at"?: string | null,"id"?: string,"records"?: number,"started_at"?: string,"status"?: string,"tenant_id"?: string
                  }
                  Relationships: [
                    {
      foreignKeyName: "connector_syncs_tenant_id_connector_id_fkey"
      columns: ["tenant_id","connector_id"]
isOneToOne: false
      referencedRelation: "connectors"
      referencedColumns: ["tenant_id","id"]
    },{
      foreignKeyName: "connector_syncs_tenant_id_fkey"
      columns: ["tenant_id"]
isOneToOne: false
      referencedRelation: "tenants"
      referencedColumns: ["id"]
    }
                  ]
                },"connectors": {
                  Row: {
                    "checkpoint": Json | null,"config": NonNullable<Json>,"config_version": number,"consecutive_failures": number,"created_at": string,"created_by": string | null,"id": string,"integration_id": string,"last_error": string | null,"last_sync_at": string | null,"name": string,"next_run_at": string,"paused_reason": string | null,"provider": string,"secret_id": string | null,"status": string,"sync_interval_seconds": number,"tenant_id": string,"updated_at": string
                  }
                  ComputedFields: never
                  Insert: {
                    "checkpoint"?: Json | null,"config"?: NonNullable<Json>,"config_version"?: number,"consecutive_failures"?: number,"created_at"?: string,"created_by"?: string | null,"id"?: string,"integration_id": string,"last_error"?: string | null,"last_sync_at"?: string | null,"name": string,"next_run_at"?: string,"paused_reason"?: string | null,"provider": string,"secret_id"?: string | null,"status"?: string,"sync_interval_seconds"?: number,"tenant_id": string,"updated_at"?: string
                  }
                  Update: {
                    "checkpoint"?: Json | null,"config"?: NonNullable<Json>,"config_version"?: number,"consecutive_failures"?: number,"created_at"?: string,"created_by"?: string | null,"id"?: string,"integration_id"?: string,"last_error"?: string | null,"last_sync_at"?: string | null,"name"?: string,"next_run_at"?: string,"paused_reason"?: string | null,"provider"?: string,"secret_id"?: string | null,"status"?: string,"sync_interval_seconds"?: number,"tenant_id"?: string,"updated_at"?: string
                  }
                  Relationships: [
                    {
      foreignKeyName: "connectors_tenant_id_fkey"
      columns: ["tenant_id"]
isOneToOne: false
      referencedRelation: "tenants"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "connectors_tenant_id_integration_id_fkey"
      columns: ["tenant_id","integration_id"]
isOneToOne: false
      referencedRelation: "integrations"
      referencedColumns: ["tenant_id","id"]
    }
                  ]
                },"correlation_mappings": {
                  Row: {
                    "created_at": string,"created_by": string | null,"id": string,"integration_id": string,"keys": NonNullable<Json>,"lookup": Json | null,"name": string,"reconcile": boolean,"tenant_id": string,"updated_at": string,"window_minutes": number
                  }
                  ComputedFields: never
                  Insert: {
                    "created_at"?: string,"created_by"?: string | null,"id"?: string,"integration_id": string,"keys": NonNullable<Json>,"lookup"?: Json | null,"name": string,"reconcile"?: boolean,"tenant_id"?: string,"updated_at"?: string,"window_minutes"?: number
                  }
                  Update: {
                    "created_at"?: string,"created_by"?: string | null,"id"?: string,"integration_id"?: string,"keys"?: NonNullable<Json>,"lookup"?: Json | null,"name"?: string,"reconcile"?: boolean,"tenant_id"?: string,"updated_at"?: string,"window_minutes"?: number
                  }
                  Relationships: [
                    {
      foreignKeyName: "correlation_mappings_tenant_id_fkey"
      columns: ["tenant_id"]
isOneToOne: false
      referencedRelation: "tenants"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "correlation_mappings_tenant_id_integration_id_fkey"
      columns: ["tenant_id","integration_id"]
isOneToOne: false
      referencedRelation: "integrations"
      referencedColumns: ["tenant_id","id"]
    }
                  ]
                },"deletion_receipts": {
                  Row: {
                    "completed_at": string,"id": string,"removed": NonNullable<Json>,"requested_at": string,"requested_by": string | null,"tenant_id": string
                  }
                  ComputedFields: never
                  Insert: {
                    "completed_at"?: string,"id"?: string,"removed"?: NonNullable<Json>,"requested_at": string,"requested_by"?: string | null,"tenant_id": string
                  }
                  Update: {
                    "completed_at"?: string,"id"?: string,"removed"?: NonNullable<Json>,"requested_at"?: string,"requested_by"?: string | null,"tenant_id"?: string
                  }
                  Relationships: [

                  ]
                },"diagnoses": {
                  Row: {
                    "attempts": number,"classification": string | null,"confidence": number | null,"created_at": string,"duration_ms": number | null,"error": string | null,"id": string,"incident_id": string,"include_knowledge_base": boolean,"input_tokens": number,"mode": string,"model": string | null,"output_tokens": number,"probable_cause": string | null,"processing_key": string,"provider": string | null,"published_at": string | null,"requested_by": string | null,"requested_mode": string,"requires_human_review": boolean,"responsible_system": string | null,"ruleset_version": string | null,"stage": string,"started_at": string | null,"status": string,"tenant_id": string,"updated_at": string,"verification_notes": NonNullable<Json>,"version": number
                  }
                  ComputedFields: never
                  Insert: {
                    "attempts"?: number,"classification"?: string | null,"confidence"?: number | null,"created_at"?: string,"duration_ms"?: number | null,"error"?: string | null,"id"?: string,"incident_id": string,"include_knowledge_base"?: boolean,"input_tokens"?: number,"mode": string,"model"?: string | null,"output_tokens"?: number,"probable_cause"?: string | null,"processing_key": string,"provider"?: string | null,"published_at"?: string | null,"requested_by"?: string | null,"requested_mode": string,"requires_human_review"?: boolean,"responsible_system"?: string | null,"ruleset_version"?: string | null,"stage"?: string,"started_at"?: string | null,"status"?: string,"tenant_id": string,"updated_at"?: string,"verification_notes"?: NonNullable<Json>,"version": number
                  }
                  Update: {
                    "attempts"?: number,"classification"?: string | null,"confidence"?: number | null,"created_at"?: string,"duration_ms"?: number | null,"error"?: string | null,"id"?: string,"incident_id"?: string,"include_knowledge_base"?: boolean,"input_tokens"?: number,"mode"?: string,"model"?: string | null,"output_tokens"?: number,"probable_cause"?: string | null,"processing_key"?: string,"provider"?: string | null,"published_at"?: string | null,"requested_by"?: string | null,"requested_mode"?: string,"requires_human_review"?: boolean,"responsible_system"?: string | null,"ruleset_version"?: string | null,"stage"?: string,"started_at"?: string | null,"status"?: string,"tenant_id"?: string,"updated_at"?: string,"verification_notes"?: NonNullable<Json>,"version"?: number
                  }
                  Relationships: [
                    {
      foreignKeyName: "diagnoses_tenant_id_fkey"
      columns: ["tenant_id"]
isOneToOne: false
      referencedRelation: "tenants"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "diagnoses_tenant_id_incident_id_fkey"
      columns: ["tenant_id","incident_id"]
isOneToOne: false
      referencedRelation: "incidents"
      referencedColumns: ["tenant_id","id"]
    }
                  ]
                },"diagnosis_evidence": {
                  Row: {
                    "chunk_id": string | null,"created_at": string,"diagnosis_id": string,"enrichment_id": string | null,"event_id": string | null,"event_timestamp": string | null,"finding": string,"global_chunk_id": string | null,"id": string,"kind": string,"label": string,"rank": number,"raw_log_object_id": string | null,"rule_match_id": string | null,"tenant_id": string,"updated_at": string
                  }
                  ComputedFields: never
                  Insert: {
                    "chunk_id"?: string | null,"created_at"?: string,"diagnosis_id": string,"enrichment_id"?: string | null,"event_id"?: string | null,"event_timestamp"?: string | null,"finding": string,"global_chunk_id"?: string | null,"id"?: string,"kind": string,"label": string,"rank": number,"raw_log_object_id"?: string | null,"rule_match_id"?: string | null,"tenant_id": string,"updated_at"?: string
                  }
                  Update: {
                    "chunk_id"?: string | null,"created_at"?: string,"diagnosis_id"?: string,"enrichment_id"?: string | null,"event_id"?: string | null,"event_timestamp"?: string | null,"finding"?: string,"global_chunk_id"?: string | null,"id"?: string,"kind"?: string,"label"?: string,"rank"?: number,"raw_log_object_id"?: string | null,"rule_match_id"?: string | null,"tenant_id"?: string,"updated_at"?: string
                  }
                  Relationships: [
                    {
      foreignKeyName: "diagnosis_evidence_enrichment_fk"
      columns: ["tenant_id","enrichment_id"]
isOneToOne: false
      referencedRelation: "enrichments"
      referencedColumns: ["tenant_id","id"]
    },{
      foreignKeyName: "diagnosis_evidence_global_chunk_id_fkey"
      columns: ["global_chunk_id"]
isOneToOne: false
      referencedRelation: "global_knowledge_chunks"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "diagnosis_evidence_tenant_id_chunk_id_fkey"
      columns: ["tenant_id","chunk_id"]
isOneToOne: false
      referencedRelation: "knowledge_chunks"
      referencedColumns: ["tenant_id","id"]
    },{
      foreignKeyName: "diagnosis_evidence_tenant_id_diagnosis_id_fkey"
      columns: ["tenant_id","diagnosis_id"]
isOneToOne: false
      referencedRelation: "diagnoses"
      referencedColumns: ["tenant_id","id"]
    },{
      foreignKeyName: "diagnosis_evidence_tenant_id_event_id_event_timestamp_fkey"
      columns: ["tenant_id","event_id","event_timestamp"]
isOneToOne: false
      referencedRelation: "events"
      referencedColumns: ["tenant_id","id","timestamp"]
    },{
      foreignKeyName: "diagnosis_evidence_tenant_id_fkey"
      columns: ["tenant_id"]
isOneToOne: false
      referencedRelation: "tenants"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "diagnosis_evidence_tenant_id_raw_log_object_id_fkey"
      columns: ["tenant_id","raw_log_object_id"]
isOneToOne: false
      referencedRelation: "raw_log_objects"
      referencedColumns: ["tenant_id","id"]
    },{
      foreignKeyName: "diagnosis_evidence_tenant_id_rule_match_id_fkey"
      columns: ["tenant_id","rule_match_id"]
isOneToOne: false
      referencedRelation: "rule_matches"
      referencedColumns: ["tenant_id","id"]
    }
                  ]
                },"diagnosis_feedback": {
                  Row: {
                    "comment": string | null,"correct_category": string | null,"correct_cause": string | null,"created_at": string,"diagnosis_id": string,"id": string,"responsible_system": string | null,"reviewer_id": string | null,"tenant_id": string,"time_to_review_s": number | null,"updated_at": string,"verdict": string
                  }
                  ComputedFields: never
                  Insert: {
                    "comment"?: string | null,"correct_category"?: string | null,"correct_cause"?: string | null,"created_at"?: string,"diagnosis_id": string,"id"?: string,"responsible_system"?: string | null,"reviewer_id"?: string | null,"tenant_id": string,"time_to_review_s"?: number | null,"updated_at"?: string,"verdict": string
                  }
                  Update: {
                    "comment"?: string | null,"correct_category"?: string | null,"correct_cause"?: string | null,"created_at"?: string,"diagnosis_id"?: string,"id"?: string,"responsible_system"?: string | null,"reviewer_id"?: string | null,"tenant_id"?: string,"time_to_review_s"?: number | null,"updated_at"?: string,"verdict"?: string
                  }
                  Relationships: [
                    {
      foreignKeyName: "diagnosis_feedback_tenant_id_diagnosis_id_fkey"
      columns: ["tenant_id","diagnosis_id"]
isOneToOne: false
      referencedRelation: "diagnoses"
      referencedColumns: ["tenant_id","id"]
    },{
      foreignKeyName: "diagnosis_feedback_tenant_id_fkey"
      columns: ["tenant_id"]
isOneToOne: false
      referencedRelation: "tenants"
      referencedColumns: ["id"]
    }
                  ]
                },"diagnosis_hypotheses": {
                  Row: {
                    "confidence": number | null,"created_at": string,"diagnosis_id": string,"id": string,"rank": number,"statement": string,"tenant_id": string,"updated_at": string
                  }
                  ComputedFields: never
                  Insert: {
                    "confidence"?: number | null,"created_at"?: string,"diagnosis_id": string,"id"?: string,"rank": number,"statement": string,"tenant_id": string,"updated_at"?: string
                  }
                  Update: {
                    "confidence"?: number | null,"created_at"?: string,"diagnosis_id"?: string,"id"?: string,"rank"?: number,"statement"?: string,"tenant_id"?: string,"updated_at"?: string
                  }
                  Relationships: [
                    {
      foreignKeyName: "diagnosis_hypotheses_tenant_id_diagnosis_id_fkey"
      columns: ["tenant_id","diagnosis_id"]
isOneToOne: false
      referencedRelation: "diagnoses"
      referencedColumns: ["tenant_id","id"]
    },{
      foreignKeyName: "diagnosis_hypotheses_tenant_id_fkey"
      columns: ["tenant_id"]
isOneToOne: false
      referencedRelation: "tenants"
      referencedColumns: ["id"]
    }
                  ]
                },"diagnosis_recommendations": {
                  Row: {
                    "created_at": string,"diagnosis_id": string,"id": string,"kind": string,"rank": number,"tenant_id": string,"text": string,"updated_at": string
                  }
                  ComputedFields: never
                  Insert: {
                    "created_at"?: string,"diagnosis_id": string,"id"?: string,"kind": string,"rank": number,"tenant_id": string,"text": string,"updated_at"?: string
                  }
                  Update: {
                    "created_at"?: string,"diagnosis_id"?: string,"id"?: string,"kind"?: string,"rank"?: number,"tenant_id"?: string,"text"?: string,"updated_at"?: string
                  }
                  Relationships: [
                    {
      foreignKeyName: "diagnosis_recommendations_tenant_id_diagnosis_id_fkey"
      columns: ["tenant_id","diagnosis_id"]
isOneToOne: false
      referencedRelation: "diagnoses"
      referencedColumns: ["tenant_id","id"]
    },{
      foreignKeyName: "diagnosis_recommendations_tenant_id_fkey"
      columns: ["tenant_id"]
isOneToOne: false
      referencedRelation: "tenants"
      referencedColumns: ["id"]
    }
                  ]
                },"enrichments": {
                  Row: {
                    "checked_at": string | null,"connector_id": string | null,"created_at": string,"diagnosis_id": string,"entity": string,"error": string | null,"field": string,"id": string,"mapping_id": string | null,"outcome": string,"record_id": string | null,"record_status": string | null,"reference": string,"system": string,"tenant_id": string,"updated_at": string
                  }
                  ComputedFields: never
                  Insert: {
                    "checked_at"?: string | null,"connector_id"?: string | null,"created_at"?: string,"diagnosis_id": string,"entity": string,"error"?: string | null,"field": string,"id"?: string,"mapping_id"?: string | null,"outcome"?: string,"record_id"?: string | null,"record_status"?: string | null,"reference": string,"system": string,"tenant_id": string,"updated_at"?: string
                  }
                  Update: {
                    "checked_at"?: string | null,"connector_id"?: string | null,"created_at"?: string,"diagnosis_id"?: string,"entity"?: string,"error"?: string | null,"field"?: string,"id"?: string,"mapping_id"?: string | null,"outcome"?: string,"record_id"?: string | null,"record_status"?: string | null,"reference"?: string,"system"?: string,"tenant_id"?: string,"updated_at"?: string
                  }
                  Relationships: [
                    {
      foreignKeyName: "enrichments_tenant_id_connector_id_fkey"
      columns: ["tenant_id","connector_id"]
isOneToOne: false
      referencedRelation: "connectors"
      referencedColumns: ["tenant_id","id"]
    },{
      foreignKeyName: "enrichments_tenant_id_diagnosis_id_fkey"
      columns: ["tenant_id","diagnosis_id"]
isOneToOne: false
      referencedRelation: "diagnoses"
      referencedColumns: ["tenant_id","id"]
    },{
      foreignKeyName: "enrichments_tenant_id_fkey"
      columns: ["tenant_id"]
isOneToOne: false
      referencedRelation: "tenants"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "enrichments_tenant_id_mapping_id_fkey"
      columns: ["tenant_id","mapping_id"]
isOneToOne: false
      referencedRelation: "correlation_mappings"
      referencedColumns: ["tenant_id","id"]
    }
                  ]
                },"events": {
                  Row: {
                    "attributes": Json | null,"business_context": Json | null,"business_reference": string | null,"correlated_by": string | null,"cross_keys": (string)[] | null,"dedup_key": string,"error": Json | null,"execution_id": string | null,"execution_ref": string | null,"id": string,"ingested_at": string,"integration_id": string,"operation": string,"raw_log_object_id": string | null,"sanitization_report": Json | null,"schema_version": string,"severity": string,"source": NonNullable<Json>,"tenant_id": string,"timestamp": string,"trace_id": string | null
                  }
                  ComputedFields: never
                  Insert: {
                    "attributes"?: Json | null,"business_context"?: Json | null,"business_reference"?: string | null,"correlated_by"?: string | null,"cross_keys"?: (string)[] | null,"dedup_key": string,"error"?: Json | null,"execution_id"?: string | null,"execution_ref"?: string | null,"id": string,"ingested_at"?: string,"integration_id": string,"operation": string,"raw_log_object_id"?: string | null,"sanitization_report"?: Json | null,"schema_version": string,"severity": string,"source": NonNullable<Json>,"tenant_id": string,"timestamp": string,"trace_id"?: string | null
                  }
                  Update: {
                    "attributes"?: Json | null,"business_context"?: Json | null,"business_reference"?: string | null,"correlated_by"?: string | null,"cross_keys"?: (string)[] | null,"dedup_key"?: string,"error"?: Json | null,"execution_id"?: string | null,"execution_ref"?: string | null,"id"?: string,"ingested_at"?: string,"integration_id"?: string,"operation"?: string,"raw_log_object_id"?: string | null,"sanitization_report"?: Json | null,"schema_version"?: string,"severity"?: string,"source"?: NonNullable<Json>,"tenant_id"?: string,"timestamp"?: string,"trace_id"?: string | null
                  }
                  Relationships: [
                    {
      foreignKeyName: "events_execution_fk"
      columns: ["tenant_id","execution_ref"]
isOneToOne: false
      referencedRelation: "executions"
      referencedColumns: ["tenant_id","id"]
    },{
      foreignKeyName: "events_tenant_id_fkey"
      columns: ["tenant_id"]
isOneToOne: false
      referencedRelation: "tenants"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "events_tenant_id_integration_id_fkey"
      columns: ["tenant_id","integration_id"]
isOneToOne: false
      referencedRelation: "integrations"
      referencedColumns: ["tenant_id","id"]
    },{
      foreignKeyName: "events_tenant_id_raw_log_object_id_fkey"
      columns: ["tenant_id","raw_log_object_id"]
isOneToOne: false
      referencedRelation: "raw_log_objects"
      referencedColumns: ["tenant_id","id"]
    }
                  ]
                },"events_2026_10": {
                  Row: {
                    "attributes": Json | null,"business_context": Json | null,"business_reference": string | null,"correlated_by": string | null,"cross_keys": (string)[] | null,"dedup_key": string,"error": Json | null,"execution_id": string | null,"execution_ref": string | null,"id": string,"ingested_at": string,"integration_id": string,"operation": string,"raw_log_object_id": string | null,"sanitization_report": Json | null,"schema_version": string,"severity": string,"source": NonNullable<Json>,"tenant_id": string,"timestamp": string,"trace_id": string | null
                  }
                  ComputedFields: never
                  Insert: {
                    "attributes"?: Json | null,"business_context"?: Json | null,"business_reference"?: string | null,"correlated_by"?: string | null,"cross_keys"?: (string)[] | null,"dedup_key": string,"error"?: Json | null,"execution_id"?: string | null,"execution_ref"?: string | null,"id": string,"ingested_at"?: string,"integration_id": string,"operation": string,"raw_log_object_id"?: string | null,"sanitization_report"?: Json | null,"schema_version": string,"severity": string,"source": NonNullable<Json>,"tenant_id": string,"timestamp": string,"trace_id"?: string | null
                  }
                  Update: {
                    "attributes"?: Json | null,"business_context"?: Json | null,"business_reference"?: string | null,"correlated_by"?: string | null,"cross_keys"?: (string)[] | null,"dedup_key"?: string,"error"?: Json | null,"execution_id"?: string | null,"execution_ref"?: string | null,"id"?: string,"ingested_at"?: string,"integration_id"?: string,"operation"?: string,"raw_log_object_id"?: string | null,"sanitization_report"?: Json | null,"schema_version"?: string,"severity"?: string,"source"?: NonNullable<Json>,"tenant_id"?: string,"timestamp"?: string,"trace_id"?: string | null
                  }
                  Relationships: [

                  ]
                },"events_2026_11": {
                  Row: {
                    "attributes": Json | null,"business_context": Json | null,"business_reference": string | null,"correlated_by": string | null,"cross_keys": (string)[] | null,"dedup_key": string,"error": Json | null,"execution_id": string | null,"execution_ref": string | null,"id": string,"ingested_at": string,"integration_id": string,"operation": string,"raw_log_object_id": string | null,"sanitization_report": Json | null,"schema_version": string,"severity": string,"source": NonNullable<Json>,"tenant_id": string,"timestamp": string,"trace_id": string | null
                  }
                  ComputedFields: never
                  Insert: {
                    "attributes"?: Json | null,"business_context"?: Json | null,"business_reference"?: string | null,"correlated_by"?: string | null,"cross_keys"?: (string)[] | null,"dedup_key": string,"error"?: Json | null,"execution_id"?: string | null,"execution_ref"?: string | null,"id": string,"ingested_at"?: string,"integration_id": string,"operation": string,"raw_log_object_id"?: string | null,"sanitization_report"?: Json | null,"schema_version": string,"severity": string,"source": NonNullable<Json>,"tenant_id": string,"timestamp": string,"trace_id"?: string | null
                  }
                  Update: {
                    "attributes"?: Json | null,"business_context"?: Json | null,"business_reference"?: string | null,"correlated_by"?: string | null,"cross_keys"?: (string)[] | null,"dedup_key"?: string,"error"?: Json | null,"execution_id"?: string | null,"execution_ref"?: string | null,"id"?: string,"ingested_at"?: string,"integration_id"?: string,"operation"?: string,"raw_log_object_id"?: string | null,"sanitization_report"?: Json | null,"schema_version"?: string,"severity"?: string,"source"?: NonNullable<Json>,"tenant_id"?: string,"timestamp"?: string,"trace_id"?: string | null
                  }
                  Relationships: [

                  ]
                },"events_2026_12": {
                  Row: {
                    "attributes": Json | null,"business_context": Json | null,"business_reference": string | null,"correlated_by": string | null,"cross_keys": (string)[] | null,"dedup_key": string,"error": Json | null,"execution_id": string | null,"execution_ref": string | null,"id": string,"ingested_at": string,"integration_id": string,"operation": string,"raw_log_object_id": string | null,"sanitization_report": Json | null,"schema_version": string,"severity": string,"source": NonNullable<Json>,"tenant_id": string,"timestamp": string,"trace_id": string | null
                  }
                  ComputedFields: never
                  Insert: {
                    "attributes"?: Json | null,"business_context"?: Json | null,"business_reference"?: string | null,"correlated_by"?: string | null,"cross_keys"?: (string)[] | null,"dedup_key": string,"error"?: Json | null,"execution_id"?: string | null,"execution_ref"?: string | null,"id": string,"ingested_at"?: string,"integration_id": string,"operation": string,"raw_log_object_id"?: string | null,"sanitization_report"?: Json | null,"schema_version": string,"severity": string,"source": NonNullable<Json>,"tenant_id": string,"timestamp": string,"trace_id"?: string | null
                  }
                  Update: {
                    "attributes"?: Json | null,"business_context"?: Json | null,"business_reference"?: string | null,"correlated_by"?: string | null,"cross_keys"?: (string)[] | null,"dedup_key"?: string,"error"?: Json | null,"execution_id"?: string | null,"execution_ref"?: string | null,"id"?: string,"ingested_at"?: string,"integration_id"?: string,"operation"?: string,"raw_log_object_id"?: string | null,"sanitization_report"?: Json | null,"schema_version"?: string,"severity"?: string,"source"?: NonNullable<Json>,"tenant_id"?: string,"timestamp"?: string,"trace_id"?: string | null
                  }
                  Relationships: [

                  ]
                },"execution_merges": {
                  Row: {
                    "id": string,"merged_at": string,"merged_id": string,"merged_keys": NonNullable<Json>,"survivor_id": string,"tenant_id": string,"updated_at": string
                  }
                  ComputedFields: never
                  Insert: {
                    "id"?: string,"merged_at"?: string,"merged_id": string,"merged_keys"?: NonNullable<Json>,"survivor_id": string,"tenant_id": string,"updated_at"?: string
                  }
                  Update: {
                    "id"?: string,"merged_at"?: string,"merged_id"?: string,"merged_keys"?: NonNullable<Json>,"survivor_id"?: string,"tenant_id"?: string,"updated_at"?: string
                  }
                  Relationships: [
                    {
      foreignKeyName: "execution_merges_tenant_id_fkey"
      columns: ["tenant_id"]
isOneToOne: false
      referencedRelation: "tenants"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "execution_merges_tenant_id_merged_id_fkey"
      columns: ["tenant_id","merged_id"]
isOneToOne: false
      referencedRelation: "executions"
      referencedColumns: ["tenant_id","id"]
    },{
      foreignKeyName: "execution_merges_tenant_id_survivor_id_fkey"
      columns: ["tenant_id","survivor_id"]
isOneToOne: false
      referencedRelation: "executions"
      referencedColumns: ["tenant_id","id"]
    }
                  ]
                },"execution_stats_dirty": {
                  Row: {
                    "hour": string,"integration_id": string,"queued_at": string,"tenant_id": string
                  }
                  ComputedFields: never
                  Insert: {
                    "hour": string,"integration_id": string,"queued_at"?: string,"tenant_id": string
                  }
                  Update: {
                    "hour"?: string,"integration_id"?: string,"queued_at"?: string,"tenant_id"?: string
                  }
                  Relationships: [

                  ]
                },"execution_stats_hourly": {
                  Row: {
                    "by_category": NonNullable<Json>,"failed": number,"hour": string,"id": string,"integration_id": string,"tenant_id": string,"total": number,"updated_at": string
                  }
                  ComputedFields: never
                  Insert: {
                    "by_category"?: NonNullable<Json>,"failed"?: number,"hour": string,"id"?: string,"integration_id": string,"tenant_id": string,"total"?: number,"updated_at"?: string
                  }
                  Update: {
                    "by_category"?: NonNullable<Json>,"failed"?: number,"hour"?: string,"id"?: string,"integration_id"?: string,"tenant_id"?: string,"total"?: number,"updated_at"?: string
                  }
                  Relationships: [
                    {
      foreignKeyName: "execution_stats_hourly_tenant_id_fkey"
      columns: ["tenant_id"]
isOneToOne: false
      referencedRelation: "tenants"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "execution_stats_hourly_tenant_id_integration_id_fkey"
      columns: ["tenant_id","integration_id"]
isOneToOne: false
      referencedRelation: "integrations"
      referencedColumns: ["tenant_id","id"]
    }
                  ]
                },"executions": {
                  Row: {
                    "closed_at": string | null,"correlation_keys": NonNullable<Json>,"created_at": string,"duration_ms": number,"event_count": number,"first_event_at": string,"id": string,"integration_id": string,"last_activity_at": string,"last_event_at": string,"low_confidence": boolean,"merged_into": string | null,"reconciled_at": string | null,"status": string,"tenant_id": string,"updated_at": string
                  }
                  ComputedFields: never
                  Insert: {
                    "closed_at"?: string | null,"correlation_keys"?: NonNullable<Json>,"created_at"?: string,"duration_ms"?: number,"event_count"?: number,"first_event_at": string,"id"?: string,"integration_id": string,"last_activity_at"?: string,"last_event_at": string,"low_confidence"?: boolean,"merged_into"?: string | null,"reconciled_at"?: string | null,"status"?: string,"tenant_id": string,"updated_at"?: string
                  }
                  Update: {
                    "closed_at"?: string | null,"correlation_keys"?: NonNullable<Json>,"created_at"?: string,"duration_ms"?: number,"event_count"?: number,"first_event_at"?: string,"id"?: string,"integration_id"?: string,"last_activity_at"?: string,"last_event_at"?: string,"low_confidence"?: boolean,"merged_into"?: string | null,"reconciled_at"?: string | null,"status"?: string,"tenant_id"?: string,"updated_at"?: string
                  }
                  Relationships: [
                    {
      foreignKeyName: "executions_tenant_id_fkey"
      columns: ["tenant_id"]
isOneToOne: false
      referencedRelation: "tenants"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "executions_tenant_id_integration_id_fkey"
      columns: ["tenant_id","integration_id"]
isOneToOne: false
      referencedRelation: "integrations"
      referencedColumns: ["tenant_id","id"]
    },{
      foreignKeyName: "executions_tenant_id_merged_into_fkey"
      columns: ["tenant_id","merged_into"]
isOneToOne: false
      referencedRelation: "executions"
      referencedColumns: ["tenant_id","id"]
    }
                  ]
                },"global_knowledge_chunks": {
                  Row: {
                    "content": string,"created_at": string,"document_id": string,"embedding": string | null,"embedding_model": string | null,"heading": string | null,"id": string,"metadata": NonNullable<Json>,"ordinal": number,"search_text": unknown,"tokens": number,"updated_at": string
                  }
                  ComputedFields: never
                  Insert: {
                    "content": string,"created_at"?: string,"document_id": string,"embedding"?: string | null,"embedding_model"?: string | null,"heading"?: string | null,"id"?: string,"metadata"?: NonNullable<Json>,"ordinal": number,"search_text"?: never,"tokens": number,"updated_at"?: string
                  }
                  Update: {
                    "content"?: string,"created_at"?: string,"document_id"?: string,"embedding"?: string | null,"embedding_model"?: string | null,"heading"?: string | null,"id"?: string,"metadata"?: NonNullable<Json>,"ordinal"?: number,"search_text"?: never,"tokens"?: number,"updated_at"?: string
                  }
                  Relationships: [
                    {
      foreignKeyName: "global_knowledge_chunks_document_id_fkey"
      columns: ["document_id"]
isOneToOne: false
      referencedRelation: "global_knowledge_documents"
      referencedColumns: ["id"]
    }
                  ]
                },"global_knowledge_documents": {
                  Row: {
                    "chunk_count": number,"created_at": string,"id": string,"slug": string,"title": string,"updated_at": string,"version": string
                  }
                  ComputedFields: never
                  Insert: {
                    "chunk_count"?: number,"created_at"?: string,"id"?: string,"slug": string,"title": string,"updated_at"?: string,"version": string
                  }
                  Update: {
                    "chunk_count"?: number,"created_at"?: string,"id"?: string,"slug"?: string,"title"?: string,"updated_at"?: string,"version"?: string
                  }
                  Relationships: [

                  ]
                },"idempotency_keys": {
                  Row: {
                    "created_at": string,"id": string,"key": string,"request_hash": string,"response_body": string | null,"response_status": number | null,"tenant_id": string,"user_id": string
                  }
                  ComputedFields: never
                  Insert: {
                    "created_at"?: string,"id"?: string,"key": string,"request_hash": string,"response_body"?: string | null,"response_status"?: number | null,"tenant_id": string,"user_id"?: string
                  }
                  Update: {
                    "created_at"?: string,"id"?: string,"key"?: string,"request_hash"?: string,"response_body"?: string | null,"response_status"?: number | null,"tenant_id"?: string,"user_id"?: string
                  }
                  Relationships: [
                    {
      foreignKeyName: "idempotency_keys_tenant_id_fkey"
      columns: ["tenant_id"]
isOneToOne: false
      referencedRelation: "tenants"
      referencedColumns: ["id"]
    }
                  ]
                },"import_rejections": {
                  Row: {
                    "created_at": string,"id": string,"import_id": string,"line_number": number,"reason": string,"tenant_id": string
                  }
                  ComputedFields: never
                  Insert: {
                    "created_at"?: string,"id"?: string,"import_id": string,"line_number": number,"reason": string,"tenant_id": string
                  }
                  Update: {
                    "created_at"?: string,"id"?: string,"import_id"?: string,"line_number"?: number,"reason"?: string,"tenant_id"?: string
                  }
                  Relationships: [
                    {
      foreignKeyName: "import_rejections_tenant_id_fkey"
      columns: ["tenant_id"]
isOneToOne: false
      referencedRelation: "tenants"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "import_rejections_tenant_id_import_id_fkey"
      columns: ["tenant_id","import_id"]
isOneToOne: false
      referencedRelation: "imports"
      referencedColumns: ["tenant_id","id"]
    }
                  ]
                },"imports": {
                  Row: {
                    "accepted": number,"created_at": string,"created_by": string | null,"duplicate_of": string | null,"duplicates": number,"error": string | null,"filename": string,"format": string | null,"id": string,"integration_id": string,"processing_started_at": string | null,"raw_log_object_id": string | null,"rejected": number,"secrets_removed": number,"sha256": string,"size_bytes": number,"status": string,"tenant_id": string,"total_lines": number,"updated_at": string
                  }
                  ComputedFields: never
                  Insert: {
                    "accepted"?: number,"created_at"?: string,"created_by"?: string | null,"duplicate_of"?: string | null,"duplicates"?: number,"error"?: string | null,"filename": string,"format"?: string | null,"id"?: string,"integration_id": string,"processing_started_at"?: string | null,"raw_log_object_id"?: string | null,"rejected"?: number,"secrets_removed"?: number,"sha256": string,"size_bytes": number,"status"?: string,"tenant_id": string,"total_lines"?: number,"updated_at"?: string
                  }
                  Update: {
                    "accepted"?: number,"created_at"?: string,"created_by"?: string | null,"duplicate_of"?: string | null,"duplicates"?: number,"error"?: string | null,"filename"?: string,"format"?: string | null,"id"?: string,"integration_id"?: string,"processing_started_at"?: string | null,"raw_log_object_id"?: string | null,"rejected"?: number,"secrets_removed"?: number,"sha256"?: string,"size_bytes"?: number,"status"?: string,"tenant_id"?: string,"total_lines"?: number,"updated_at"?: string
                  }
                  Relationships: [
                    {
      foreignKeyName: "imports_tenant_id_duplicate_of_fkey"
      columns: ["tenant_id","duplicate_of"]
isOneToOne: false
      referencedRelation: "imports"
      referencedColumns: ["tenant_id","id"]
    },{
      foreignKeyName: "imports_tenant_id_fkey"
      columns: ["tenant_id"]
isOneToOne: false
      referencedRelation: "tenants"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "imports_tenant_id_integration_id_fkey"
      columns: ["tenant_id","integration_id"]
isOneToOne: false
      referencedRelation: "integrations"
      referencedColumns: ["tenant_id","id"]
    },{
      foreignKeyName: "imports_tenant_id_raw_log_object_id_fkey"
      columns: ["tenant_id","raw_log_object_id"]
isOneToOne: false
      referencedRelation: "raw_log_objects"
      referencedColumns: ["tenant_id","id"]
    }
                  ]
                },"incident_comments": {
                  Row: {
                    "author_id": string | null,"body_md": string,"created_at": string,"edited_at": string | null,"external_author": string | null,"external_id": string | null,"id": string,"incident_id": string,"mentions": (string)[],"tenant_id": string,"updated_at": string
                  }
                  ComputedFields: never
                  Insert: {
                    "author_id"?: string | null,"body_md": string,"created_at"?: string,"edited_at"?: string | null,"external_author"?: string | null,"external_id"?: string | null,"id"?: string,"incident_id": string,"mentions"?: (string)[],"tenant_id": string,"updated_at"?: string
                  }
                  Update: {
                    "author_id"?: string | null,"body_md"?: string,"created_at"?: string,"edited_at"?: string | null,"external_author"?: string | null,"external_id"?: string | null,"id"?: string,"incident_id"?: string,"mentions"?: (string)[],"tenant_id"?: string,"updated_at"?: string
                  }
                  Relationships: [
                    {
      foreignKeyName: "incident_comments_tenant_id_fkey"
      columns: ["tenant_id"]
isOneToOne: false
      referencedRelation: "tenants"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "incident_comments_tenant_id_incident_id_fkey"
      columns: ["tenant_id","incident_id"]
isOneToOne: false
      referencedRelation: "incidents"
      referencedColumns: ["tenant_id","id"]
    }
                  ]
                },"incident_counters": {
                  Row: {
                    "last_number": number,"tenant_id": string,"updated_at": string
                  }
                  ComputedFields: never
                  Insert: {
                    "last_number"?: number,"tenant_id": string,"updated_at"?: string
                  }
                  Update: {
                    "last_number"?: number,"tenant_id"?: string,"updated_at"?: string
                  }
                  Relationships: [
                    {
      foreignKeyName: "incident_counters_tenant_id_fkey"
      columns: ["tenant_id"]
isOneToOne: true
      referencedRelation: "tenants"
      referencedColumns: ["id"]
    }
                  ]
                },"incident_executions": {
                  Row: {
                    "created_at": string,"execution_id": string,"id": string,"incident_id": string,"tenant_id": string,"updated_at": string
                  }
                  ComputedFields: never
                  Insert: {
                    "created_at"?: string,"execution_id": string,"id"?: string,"incident_id": string,"tenant_id": string,"updated_at"?: string
                  }
                  Update: {
                    "created_at"?: string,"execution_id"?: string,"id"?: string,"incident_id"?: string,"tenant_id"?: string,"updated_at"?: string
                  }
                  Relationships: [
                    {
      foreignKeyName: "incident_executions_tenant_id_execution_id_fkey"
      columns: ["tenant_id","execution_id"]
isOneToOne: true
      referencedRelation: "executions"
      referencedColumns: ["tenant_id","id"]
    },{
      foreignKeyName: "incident_executions_tenant_id_fkey"
      columns: ["tenant_id"]
isOneToOne: false
      referencedRelation: "tenants"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "incident_executions_tenant_id_incident_id_fkey"
      columns: ["tenant_id","incident_id"]
isOneToOne: false
      referencedRelation: "incidents"
      referencedColumns: ["tenant_id","id"]
    }
                  ]
                },"incident_history": {
                  Row: {
                    "action": string,"actor_id": string | null,"created_at": string,"from_value": string | null,"id": string,"incident_id": string,"note": string | null,"tenant_id": string,"to_value": string | null,"updated_at": string
                  }
                  ComputedFields: never
                  Insert: {
                    "action": string,"actor_id"?: string | null,"created_at"?: string,"from_value"?: string | null,"id"?: string,"incident_id": string,"note"?: string | null,"tenant_id": string,"to_value"?: string | null,"updated_at"?: string
                  }
                  Update: {
                    "action"?: string,"actor_id"?: string | null,"created_at"?: string,"from_value"?: string | null,"id"?: string,"incident_id"?: string,"note"?: string | null,"tenant_id"?: string,"to_value"?: string | null,"updated_at"?: string
                  }
                  Relationships: [
                    {
      foreignKeyName: "incident_history_tenant_id_fkey"
      columns: ["tenant_id"]
isOneToOne: false
      referencedRelation: "tenants"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "incident_history_tenant_id_incident_id_fkey"
      columns: ["tenant_id","incident_id"]
isOneToOne: false
      referencedRelation: "incidents"
      referencedColumns: ["tenant_id","id"]
    }
                  ]
                },"incident_tickets": {
                  Row: {
                    "assignment_group": string | null,"claimed_at": string | null,"comments_synced_at": string | null,"created_at": string,"error": string | null,"external_id": string | null,"external_key": string | null,"external_status": string | null,"id": string,"incident_id": string,"last_synced_at": string | null,"provider": string,"requested_by": string | null,"rule_id": string | null,"status": string,"tenant_id": string,"updated_at": string,"url": string | null
                  }
                  ComputedFields: never
                  Insert: {
                    "assignment_group"?: string | null,"claimed_at"?: string | null,"comments_synced_at"?: string | null,"created_at"?: string,"error"?: string | null,"external_id"?: string | null,"external_key"?: string | null,"external_status"?: string | null,"id"?: string,"incident_id": string,"last_synced_at"?: string | null,"provider"?: string,"requested_by"?: string | null,"rule_id"?: string | null,"status"?: string,"tenant_id": string,"updated_at"?: string,"url"?: string | null
                  }
                  Update: {
                    "assignment_group"?: string | null,"claimed_at"?: string | null,"comments_synced_at"?: string | null,"created_at"?: string,"error"?: string | null,"external_id"?: string | null,"external_key"?: string | null,"external_status"?: string | null,"id"?: string,"incident_id"?: string,"last_synced_at"?: string | null,"provider"?: string,"requested_by"?: string | null,"rule_id"?: string | null,"status"?: string,"tenant_id"?: string,"updated_at"?: string,"url"?: string | null
                  }
                  Relationships: [
                    {
      foreignKeyName: "incident_tickets_tenant_id_fkey"
      columns: ["tenant_id"]
isOneToOne: false
      referencedRelation: "tenants"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "incident_tickets_tenant_id_incident_id_fkey"
      columns: ["tenant_id","incident_id"]
isOneToOne: false
      referencedRelation: "incidents"
      referencedColumns: ["tenant_id","id"]
    },{
      foreignKeyName: "incident_tickets_tenant_id_rule_id_fkey"
      columns: ["tenant_id","rule_id"]
isOneToOne: false
      referencedRelation: "alert_rules"
      referencedColumns: ["tenant_id","id"]
    }
                  ]
                },"incidents": {
                  Row: {
                    "assignee_id": string | null,"category": string,"created_at": string,"execution_count": number,"first_seen_at": string,"id": string,"integration_id": string,"last_seen_at": string,"number": number,"resolution_note": string | null,"resolved_at": string | null,"rule_code": string,"rule_version": string,"severity": string,"status": string,"tenant_id": string,"title": string,"updated_at": string,"incident_snapshot": Json | null
                  }
                  ComputedFields: "incident_snapshot"
                  Insert: {
                    "assignee_id"?: string | null,"category": string,"created_at"?: string,"execution_count"?: number,"first_seen_at": string,"id"?: string,"integration_id": string,"last_seen_at": string,"number": number,"resolution_note"?: string | null,"resolved_at"?: string | null,"rule_code": string,"rule_version": string,"severity": string,"status"?: string,"tenant_id": string,"title": string,"updated_at"?: string
                  }
                  Update: {
                    "assignee_id"?: string | null,"category"?: string,"created_at"?: string,"execution_count"?: number,"first_seen_at"?: string,"id"?: string,"integration_id"?: string,"last_seen_at"?: string,"number"?: number,"resolution_note"?: string | null,"resolved_at"?: string | null,"rule_code"?: string,"rule_version"?: string,"severity"?: string,"status"?: string,"tenant_id"?: string,"title"?: string,"updated_at"?: string
                  }
                  Relationships: [
                    {
      foreignKeyName: "incidents_rule_code_rule_version_fkey"
      columns: ["rule_code","rule_version"]
isOneToOne: false
      referencedRelation: "rule_definitions"
      referencedColumns: ["code","version"]
    },{
      foreignKeyName: "incidents_tenant_id_fkey"
      columns: ["tenant_id"]
isOneToOne: false
      referencedRelation: "tenants"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "incidents_tenant_id_integration_id_fkey"
      columns: ["tenant_id","integration_id"]
isOneToOne: false
      referencedRelation: "integrations"
      referencedColumns: ["tenant_id","id"]
    }
                  ]
                },"ingestion_batches": {
                  Row: {
                    "agent_id": string | null,"connector_id": string | null,"created_at": string,"error": string | null,"event_count": number,"events": NonNullable<Json>,"expires_at": string,"failed_at": string | null,"id": string,"integration_id": string,"processed_at": string | null,"skipped": number,"tenant_id": string,"token_id": string | null
                  }
                  ComputedFields: never
                  Insert: {
                    "agent_id"?: string | null,"connector_id"?: string | null,"created_at"?: string,"error"?: string | null,"event_count": number,"events": NonNullable<Json>,"expires_at"?: string,"failed_at"?: string | null,"id"?: string,"integration_id": string,"processed_at"?: string | null,"skipped"?: number,"tenant_id": string,"token_id"?: string | null
                  }
                  Update: {
                    "agent_id"?: string | null,"connector_id"?: string | null,"created_at"?: string,"error"?: string | null,"event_count"?: number,"events"?: NonNullable<Json>,"expires_at"?: string,"failed_at"?: string | null,"id"?: string,"integration_id"?: string,"processed_at"?: string | null,"skipped"?: number,"tenant_id"?: string,"token_id"?: string | null
                  }
                  Relationships: [
                    {
      foreignKeyName: "ingestion_batches_agent_fk"
      columns: ["tenant_id","agent_id"]
isOneToOne: false
      referencedRelation: "agents"
      referencedColumns: ["tenant_id","id"]
    },{
      foreignKeyName: "ingestion_batches_connector_fk"
      columns: ["tenant_id","connector_id"]
isOneToOne: false
      referencedRelation: "connectors"
      referencedColumns: ["tenant_id","id"]
    },{
      foreignKeyName: "ingestion_batches_tenant_id_fkey"
      columns: ["tenant_id"]
isOneToOne: false
      referencedRelation: "tenants"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "ingestion_batches_tenant_id_integration_id_fkey"
      columns: ["tenant_id","integration_id"]
isOneToOne: false
      referencedRelation: "integrations"
      referencedColumns: ["tenant_id","id"]
    },{
      foreignKeyName: "ingestion_batches_tenant_id_token_id_fkey"
      columns: ["tenant_id","token_id"]
isOneToOne: false
      referencedRelation: "ingestion_tokens"
      referencedColumns: ["tenant_id","id"]
    }
                  ]
                },"ingestion_tokens": {
                  Row: {
                    "created_at": string,"created_by": string | null,"id": string,"integration_id": string,"last_used_at": string | null,"name": string,"prefix": string,"revoked_at": string | null,"tenant_id": string,"token_hash": string
                  }
                  ComputedFields: never
                  Insert: {
                    "created_at"?: string,"created_by"?: string | null,"id"?: string,"integration_id": string,"last_used_at"?: string | null,"name": string,"prefix": string,"revoked_at"?: string | null,"tenant_id": string,"token_hash": string
                  }
                  Update: {
                    "created_at"?: string,"created_by"?: string | null,"id"?: string,"integration_id"?: string,"last_used_at"?: string | null,"name"?: string,"prefix"?: string,"revoked_at"?: string | null,"tenant_id"?: string,"token_hash"?: string
                  }
                  Relationships: [
                    {
      foreignKeyName: "ingestion_tokens_tenant_id_fkey"
      columns: ["tenant_id"]
isOneToOne: false
      referencedRelation: "tenants"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "ingestion_tokens_tenant_id_integration_id_fkey"
      columns: ["tenant_id","integration_id"]
isOneToOne: false
      referencedRelation: "integrations"
      referencedColumns: ["tenant_id","id"]
    }
                  ]
                },"integrations": {
                  Row: {
                    "archived_at": string | null,"created_at": string,"created_by": string | null,"description": string | null,"environment": string,"id": string,"name": string,"owner_team": string | null,"source_system": string,"target_system": string,"tenant_id": string,"updated_at": string
                  }
                  ComputedFields: never
                  Insert: {
                    "archived_at"?: string | null,"created_at"?: string,"created_by"?: string | null,"description"?: string | null,"environment": string,"id"?: string,"name": string,"owner_team"?: string | null,"source_system": string,"target_system": string,"tenant_id"?: string,"updated_at"?: string
                  }
                  Update: {
                    "archived_at"?: string | null,"created_at"?: string,"created_by"?: string | null,"description"?: string | null,"environment"?: string,"id"?: string,"name"?: string,"owner_team"?: string | null,"source_system"?: string,"target_system"?: string,"tenant_id"?: string,"updated_at"?: string
                  }
                  Relationships: [
                    {
      foreignKeyName: "integrations_tenant_id_fkey"
      columns: ["tenant_id"]
isOneToOne: false
      referencedRelation: "tenants"
      referencedColumns: ["id"]
    }
                  ]
                },"invitations": {
                  Row: {
                    "accepted_at": string | null,"created_at": string,"email": string,"expires_at": string,"id": string,"invited_by": string | null,"role": string,"tenant_id": string,"token_hash": string,"updated_at": string
                  }
                  ComputedFields: never
                  Insert: {
                    "accepted_at"?: string | null,"created_at"?: string,"email": string,"expires_at"?: string,"id"?: string,"invited_by"?: string | null,"role": string,"tenant_id": string,"token_hash": string,"updated_at"?: string
                  }
                  Update: {
                    "accepted_at"?: string | null,"created_at"?: string,"email"?: string,"expires_at"?: string,"id"?: string,"invited_by"?: string | null,"role"?: string,"tenant_id"?: string,"token_hash"?: string,"updated_at"?: string
                  }
                  Relationships: [
                    {
      foreignKeyName: "invitations_tenant_id_fkey"
      columns: ["tenant_id"]
isOneToOne: false
      referencedRelation: "tenants"
      referencedColumns: ["id"]
    }
                  ]
                },"itsm_connections": {
                  Row: {
                    "assignment_groups": NonNullable<Json>,"client_id": string | null,"cloud_id": string | null,"created_at": string,"created_by": string | null,"custom_fields": NonNullable<Json>,"default_group": string | null,"hook_token_hash": string | null,"id": string,"impact_map": NonNullable<Json>,"instance_url": string | null,"issue_type": string | null,"jira_webhook_expires_at": string | null,"jira_webhook_id": number | null,"last_error": string | null,"priority_map": NonNullable<Json>,"project_key": string | null,"provider": string,"secret_id": string | null,"site_url": string | null,"sites": NonNullable<Json>,"status": string,"sync_status": boolean,"tenant_id": string,"updated_at": string
                  }
                  ComputedFields: never
                  Insert: {
                    "assignment_groups"?: NonNullable<Json>,"client_id"?: string | null,"cloud_id"?: string | null,"created_at"?: string,"created_by"?: string | null,"custom_fields"?: NonNullable<Json>,"default_group"?: string | null,"hook_token_hash"?: string | null,"id"?: string,"impact_map"?: NonNullable<Json>,"instance_url"?: string | null,"issue_type"?: string | null,"jira_webhook_expires_at"?: string | null,"jira_webhook_id"?: number | null,"last_error"?: string | null,"priority_map"?: NonNullable<Json>,"project_key"?: string | null,"provider"?: string,"secret_id"?: string | null,"site_url"?: string | null,"sites"?: NonNullable<Json>,"status"?: string,"sync_status"?: boolean,"tenant_id": string,"updated_at"?: string
                  }
                  Update: {
                    "assignment_groups"?: NonNullable<Json>,"client_id"?: string | null,"cloud_id"?: string | null,"created_at"?: string,"created_by"?: string | null,"custom_fields"?: NonNullable<Json>,"default_group"?: string | null,"hook_token_hash"?: string | null,"id"?: string,"impact_map"?: NonNullable<Json>,"instance_url"?: string | null,"issue_type"?: string | null,"jira_webhook_expires_at"?: string | null,"jira_webhook_id"?: number | null,"last_error"?: string | null,"priority_map"?: NonNullable<Json>,"project_key"?: string | null,"provider"?: string,"secret_id"?: string | null,"site_url"?: string | null,"sites"?: NonNullable<Json>,"status"?: string,"sync_status"?: boolean,"tenant_id"?: string,"updated_at"?: string
                  }
                  Relationships: [
                    {
      foreignKeyName: "itsm_connections_tenant_id_fkey"
      columns: ["tenant_id"]
isOneToOne: false
      referencedRelation: "tenants"
      referencedColumns: ["id"]
    }
                  ]
                },"itsm_oauth_states": {
                  Row: {
                    "created_at": string,"expires_at": string,"id": string,"state_hash": string,"tenant_id": string,"used_at": string | null,"user_id": string
                  }
                  ComputedFields: never
                  Insert: {
                    "created_at"?: string,"expires_at"?: string,"id"?: string,"state_hash": string,"tenant_id": string,"used_at"?: string | null,"user_id": string
                  }
                  Update: {
                    "created_at"?: string,"expires_at"?: string,"id"?: string,"state_hash"?: string,"tenant_id"?: string,"used_at"?: string | null,"user_id"?: string
                  }
                  Relationships: [
                    {
      foreignKeyName: "itsm_oauth_states_tenant_id_fkey"
      columns: ["tenant_id"]
isOneToOne: false
      referencedRelation: "tenants"
      referencedColumns: ["id"]
    }
                  ]
                },"knowledge_chunks": {
                  Row: {
                    "content": string,"created_at": string,"document_id": string,"embedding": string | null,"embedding_model": string | null,"heading": string | null,"id": string,"metadata": NonNullable<Json>,"ordinal": number,"search_text": unknown,"tenant_id": string,"tokens": number,"updated_at": string
                  }
                  ComputedFields: never
                  Insert: {
                    "content": string,"created_at"?: string,"document_id": string,"embedding"?: string | null,"embedding_model"?: string | null,"heading"?: string | null,"id"?: string,"metadata"?: NonNullable<Json>,"ordinal": number,"search_text"?: never,"tenant_id": string,"tokens": number,"updated_at"?: string
                  }
                  Update: {
                    "content"?: string,"created_at"?: string,"document_id"?: string,"embedding"?: string | null,"embedding_model"?: string | null,"heading"?: string | null,"id"?: string,"metadata"?: NonNullable<Json>,"ordinal"?: number,"search_text"?: never,"tenant_id"?: string,"tokens"?: number,"updated_at"?: string
                  }
                  Relationships: [
                    {
      foreignKeyName: "knowledge_chunks_tenant_id_document_id_fkey"
      columns: ["tenant_id","document_id"]
isOneToOne: false
      referencedRelation: "knowledge_documents"
      referencedColumns: ["tenant_id","id"]
    },{
      foreignKeyName: "knowledge_chunks_tenant_id_fkey"
      columns: ["tenant_id"]
isOneToOne: false
      referencedRelation: "tenants"
      referencedColumns: ["id"]
    }
                  ]
                },"knowledge_documents": {
                  Row: {
                    "body": string | null,"chunk_count": number,"content_type": string | null,"created_at": string,"created_by": string | null,"embedding_model": string | null,"error": string | null,"id": string,"incident_id": string | null,"reindex_queued_at": string | null,"size_bytes": number | null,"source": string,"status": string,"storage_path": string | null,"tenant_id": string,"title": string,"updated_at": string
                  }
                  ComputedFields: never
                  Insert: {
                    "body"?: string | null,"chunk_count"?: number,"content_type"?: string | null,"created_at"?: string,"created_by"?: string | null,"embedding_model"?: string | null,"error"?: string | null,"id"?: string,"incident_id"?: string | null,"reindex_queued_at"?: string | null,"size_bytes"?: number | null,"source": string,"status"?: string,"storage_path"?: string | null,"tenant_id": string,"title": string,"updated_at"?: string
                  }
                  Update: {
                    "body"?: string | null,"chunk_count"?: number,"content_type"?: string | null,"created_at"?: string,"created_by"?: string | null,"embedding_model"?: string | null,"error"?: string | null,"id"?: string,"incident_id"?: string | null,"reindex_queued_at"?: string | null,"size_bytes"?: number | null,"source"?: string,"status"?: string,"storage_path"?: string | null,"tenant_id"?: string,"title"?: string,"updated_at"?: string
                  }
                  Relationships: [
                    {
      foreignKeyName: "knowledge_documents_tenant_id_fkey"
      columns: ["tenant_id"]
isOneToOne: false
      referencedRelation: "tenants"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "knowledge_documents_tenant_id_incident_id_fkey"
      columns: ["tenant_id","incident_id"]
isOneToOne: false
      referencedRelation: "incidents"
      referencedColumns: ["tenant_id","id"]
    }
                  ]
                },"local_ai_settings": {
                  Row: {
                    "agent_id": string | null,"created_at": string,"endpoint_url": string | null,"id": string,"model": string,"tenant_id": string,"timeout_seconds": number,"transport": string,"updated_at": string
                  }
                  ComputedFields: never
                  Insert: {
                    "agent_id"?: string | null,"created_at"?: string,"endpoint_url"?: string | null,"id"?: string,"model": string,"tenant_id": string,"timeout_seconds"?: number,"transport": string,"updated_at"?: string
                  }
                  Update: {
                    "agent_id"?: string | null,"created_at"?: string,"endpoint_url"?: string | null,"id"?: string,"model"?: string,"tenant_id"?: string,"timeout_seconds"?: number,"transport"?: string,"updated_at"?: string
                  }
                  Relationships: [
                    {
      foreignKeyName: "local_ai_settings_tenant_id_agent_id_fkey"
      columns: ["tenant_id","agent_id"]
isOneToOne: false
      referencedRelation: "agents"
      referencedColumns: ["tenant_id","id"]
    },{
      foreignKeyName: "local_ai_settings_tenant_id_fkey"
      columns: ["tenant_id"]
isOneToOne: true
      referencedRelation: "tenants"
      referencedColumns: ["id"]
    }
                  ]
                },"local_llm_requests": {
                  Row: {
                    "agent_id": string,"claimed_at": string | null,"completed_at": string | null,"created_at": string,"error": string | null,"id": string,"request": NonNullable<Json>,"response": Json | null,"status": string,"tenant_id": string,"updated_at": string
                  }
                  ComputedFields: never
                  Insert: {
                    "agent_id": string,"claimed_at"?: string | null,"completed_at"?: string | null,"created_at"?: string,"error"?: string | null,"id"?: string,"request": NonNullable<Json>,"response"?: Json | null,"status"?: string,"tenant_id": string,"updated_at"?: string
                  }
                  Update: {
                    "agent_id"?: string,"claimed_at"?: string | null,"completed_at"?: string | null,"created_at"?: string,"error"?: string | null,"id"?: string,"request"?: NonNullable<Json>,"response"?: Json | null,"status"?: string,"tenant_id"?: string,"updated_at"?: string
                  }
                  Relationships: [
                    {
      foreignKeyName: "local_llm_requests_tenant_id_agent_id_fkey"
      columns: ["tenant_id","agent_id"]
isOneToOne: false
      referencedRelation: "agents"
      referencedColumns: ["tenant_id","id"]
    },{
      foreignKeyName: "local_llm_requests_tenant_id_fkey"
      columns: ["tenant_id"]
isOneToOne: false
      referencedRelation: "tenants"
      referencedColumns: ["id"]
    }
                  ]
                },"memberships": {
                  Row: {
                    "created_at": string,"id": string,"role": string,"tenant_id": string,"updated_at": string,"user_id": string,"require_other_owner": undefined | null
                  }
                  ComputedFields: "require_other_owner"
                  Insert: {
                    "created_at"?: string,"id"?: string,"role": string,"tenant_id": string,"updated_at"?: string,"user_id": string
                  }
                  Update: {
                    "created_at"?: string,"id"?: string,"role"?: string,"tenant_id"?: string,"updated_at"?: string,"user_id"?: string
                  }
                  Relationships: [
                    {
      foreignKeyName: "memberships_tenant_id_fkey"
      columns: ["tenant_id"]
isOneToOne: false
      referencedRelation: "tenants"
      referencedColumns: ["id"]
    }
                  ]
                },"notification_channels": {
                  Row: {
                    "config": NonNullable<Json>,"created_at": string,"created_by": string | null,"id": string,"name": string,"secret_id": string | null,"tenant_id": string,"type": string,"updated_at": string
                  }
                  ComputedFields: never
                  Insert: {
                    "config"?: NonNullable<Json>,"created_at"?: string,"created_by"?: string | null,"id"?: string,"name": string,"secret_id"?: string | null,"tenant_id": string,"type": string,"updated_at"?: string
                  }
                  Update: {
                    "config"?: NonNullable<Json>,"created_at"?: string,"created_by"?: string | null,"id"?: string,"name"?: string,"secret_id"?: string | null,"tenant_id"?: string,"type"?: string,"updated_at"?: string
                  }
                  Relationships: [
                    {
      foreignKeyName: "notification_channels_tenant_id_fkey"
      columns: ["tenant_id"]
isOneToOne: false
      referencedRelation: "tenants"
      referencedColumns: ["id"]
    }
                  ]
                },"notification_deliveries": {
                  Row: {
                    "channel_id": string | null,"created_at": string,"error": string | null,"id": string,"rule_id": string | null,"status": string,"subject": string,"tenant_id": string
                  }
                  ComputedFields: never
                  Insert: {
                    "channel_id"?: string | null,"created_at"?: string,"error"?: string | null,"id"?: string,"rule_id"?: string | null,"status": string,"subject": string,"tenant_id": string
                  }
                  Update: {
                    "channel_id"?: string | null,"created_at"?: string,"error"?: string | null,"id"?: string,"rule_id"?: string | null,"status"?: string,"subject"?: string,"tenant_id"?: string
                  }
                  Relationships: [
                    {
      foreignKeyName: "notification_deliveries_tenant_id_channel_id_fkey"
      columns: ["tenant_id","channel_id"]
isOneToOne: false
      referencedRelation: "notification_channels"
      referencedColumns: ["tenant_id","id"]
    },{
      foreignKeyName: "notification_deliveries_tenant_id_fkey"
      columns: ["tenant_id"]
isOneToOne: false
      referencedRelation: "tenants"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "notification_deliveries_tenant_id_rule_id_fkey"
      columns: ["tenant_id","rule_id"]
isOneToOne: false
      referencedRelation: "alert_rules"
      referencedColumns: ["tenant_id","id"]
    }
                  ]
                },"outbox_messages": {
                  Row: {
                    "attempts": number,"created_at": string,"id": number,"payload": NonNullable<Json>,"published_at": string | null,"tenant_id": string,"topic": string,"traceparent": string | null
                  }
                  ComputedFields: never
                  Insert: {
                    "attempts"?: number,"created_at"?: string,"id"?: never,"payload": NonNullable<Json>,"published_at"?: string | null,"tenant_id": string,"topic": string,"traceparent"?: string | null
                  }
                  Update: {
                    "attempts"?: number,"created_at"?: string,"id"?: never,"payload"?: NonNullable<Json>,"published_at"?: string | null,"tenant_id"?: string,"topic"?: string,"traceparent"?: string | null
                  }
                  Relationships: [
                    {
      foreignKeyName: "outbox_messages_tenant_id_fkey"
      columns: ["tenant_id"]
isOneToOne: false
      referencedRelation: "tenants"
      referencedColumns: ["id"]
    }
                  ]
                },"plan_limits": {
                  Row: {
                    "limit": number,"period": string,"plan": string,"resource": string
                  }
                  ComputedFields: never
                  Insert: {
                    "limit": number,"period": string,"plan": string,"resource": string
                  }
                  Update: {
                    "limit"?: number,"period"?: string,"plan"?: string,"resource"?: string
                  }
                  Relationships: [

                  ]
                },"platform_jobs": {
                  Row: {
                    "details": NonNullable<Json>,"last_success_at": string,"name": string,"updated_at": string
                  }
                  ComputedFields: never
                  Insert: {
                    "details"?: NonNullable<Json>,"last_success_at": string,"name": string,"updated_at"?: string
                  }
                  Update: {
                    "details"?: NonNullable<Json>,"last_success_at"?: string,"name"?: string,"updated_at"?: string
                  }
                  Relationships: [

                  ]
                },"push_subscriptions": {
                  Row: {
                    "auth": string,"created_at": string,"endpoint": string,"id": string,"last_success_at": string | null,"p256dh": string,"tenant_id": string,"updated_at": string,"user_agent": string | null,"user_id": string
                  }
                  ComputedFields: never
                  Insert: {
                    "auth": string,"created_at"?: string,"endpoint": string,"id"?: string,"last_success_at"?: string | null,"p256dh": string,"tenant_id"?: string,"updated_at"?: string,"user_agent"?: string | null,"user_id"?: string
                  }
                  Update: {
                    "auth"?: string,"created_at"?: string,"endpoint"?: string,"id"?: string,"last_success_at"?: string | null,"p256dh"?: string,"tenant_id"?: string,"updated_at"?: string,"user_agent"?: string | null,"user_id"?: string
                  }
                  Relationships: [
                    {
      foreignKeyName: "push_subscriptions_tenant_id_fkey"
      columns: ["tenant_id"]
isOneToOne: false
      referencedRelation: "tenants"
      referencedColumns: ["id"]
    }
                  ]
                },"raw_log_objects": {
                  Row: {
                    "created_at": string,"expires_at": string,"id": string,"sha256": string,"size_bytes": number,"source": string,"storage_path": string,"tenant_id": string
                  }
                  ComputedFields: never
                  Insert: {
                    "created_at"?: string,"expires_at"?: string,"id"?: string,"sha256": string,"size_bytes": number,"source": string,"storage_path": string,"tenant_id": string
                  }
                  Update: {
                    "created_at"?: string,"expires_at"?: string,"id"?: string,"sha256"?: string,"size_bytes"?: number,"source"?: string,"storage_path"?: string,"tenant_id"?: string
                  }
                  Relationships: [
                    {
      foreignKeyName: "raw_log_objects_tenant_id_fkey"
      columns: ["tenant_id"]
isOneToOne: false
      referencedRelation: "tenants"
      referencedColumns: ["id"]
    }
                  ]
                },"report_shares": {
                  Row: {
                    "access_count": number,"created_at": string,"created_by": string | null,"download_url": string,"expires_at": string,"id": string,"last_accessed_at": string | null,"report_id": string,"revoked_at": string | null,"revoked_by": string | null,"tenant_id": string,"token_hash": string,"updated_at": string
                  }
                  ComputedFields: never
                  Insert: {
                    "access_count"?: number,"created_at"?: string,"created_by"?: string | null,"download_url": string,"expires_at": string,"id"?: string,"last_accessed_at"?: string | null,"report_id": string,"revoked_at"?: string | null,"revoked_by"?: string | null,"tenant_id": string,"token_hash": string,"updated_at"?: string
                  }
                  Update: {
                    "access_count"?: number,"created_at"?: string,"created_by"?: string | null,"download_url"?: string,"expires_at"?: string,"id"?: string,"last_accessed_at"?: string | null,"report_id"?: string,"revoked_at"?: string | null,"revoked_by"?: string | null,"tenant_id"?: string,"token_hash"?: string,"updated_at"?: string
                  }
                  Relationships: [
                    {
      foreignKeyName: "report_shares_tenant_id_fkey"
      columns: ["tenant_id"]
isOneToOne: false
      referencedRelation: "tenants"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "report_shares_tenant_id_report_id_fkey"
      columns: ["tenant_id","report_id"]
isOneToOne: false
      referencedRelation: "reports"
      referencedColumns: ["tenant_id","id"]
    }
                  ]
                },"reports": {
                  Row: {
                    "attempts": number,"completed_at": string | null,"content_sha256": string | null,"created_at": string,"diagnosis_id": string | null,"error": string | null,"format": string,"id": string,"incident_id": string,"include_event_excerpts": boolean,"include_timeline": boolean,"processing_key": string,"requested_by": string | null,"size_bytes": number | null,"status": string,"storage_path": string | null,"tenant_id": string,"updated_at": string
                  }
                  ComputedFields: never
                  Insert: {
                    "attempts"?: number,"completed_at"?: string | null,"content_sha256"?: string | null,"created_at"?: string,"diagnosis_id"?: string | null,"error"?: string | null,"format": string,"id"?: string,"incident_id": string,"include_event_excerpts"?: boolean,"include_timeline"?: boolean,"processing_key": string,"requested_by"?: string | null,"size_bytes"?: number | null,"status"?: string,"storage_path"?: string | null,"tenant_id": string,"updated_at"?: string
                  }
                  Update: {
                    "attempts"?: number,"completed_at"?: string | null,"content_sha256"?: string | null,"created_at"?: string,"diagnosis_id"?: string | null,"error"?: string | null,"format"?: string,"id"?: string,"incident_id"?: string,"include_event_excerpts"?: boolean,"include_timeline"?: boolean,"processing_key"?: string,"requested_by"?: string | null,"size_bytes"?: number | null,"status"?: string,"storage_path"?: string | null,"tenant_id"?: string,"updated_at"?: string
                  }
                  Relationships: [
                    {
      foreignKeyName: "reports_tenant_id_diagnosis_id_fkey"
      columns: ["tenant_id","diagnosis_id"]
isOneToOne: false
      referencedRelation: "diagnoses"
      referencedColumns: ["tenant_id","id"]
    },{
      foreignKeyName: "reports_tenant_id_fkey"
      columns: ["tenant_id"]
isOneToOne: false
      referencedRelation: "tenants"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "reports_tenant_id_incident_id_fkey"
      columns: ["tenant_id","incident_id"]
isOneToOne: false
      referencedRelation: "incidents"
      referencedColumns: ["tenant_id","id"]
    }
                  ]
                },"retention_policies": {
                  Row: {
                    "created_at": string,"data_class": string,"days": number,"id": string,"tenant_id": string,"updated_at": string,"updated_by": string | null
                  }
                  ComputedFields: never
                  Insert: {
                    "created_at"?: string,"data_class": string,"days": number,"id"?: string,"tenant_id": string,"updated_at"?: string,"updated_by"?: string | null
                  }
                  Update: {
                    "created_at"?: string,"data_class"?: string,"days"?: number,"id"?: string,"tenant_id"?: string,"updated_at"?: string,"updated_by"?: string | null
                  }
                  Relationships: [
                    {
      foreignKeyName: "retention_policies_tenant_id_fkey"
      columns: ["tenant_id"]
isOneToOne: false
      referencedRelation: "tenants"
      referencedColumns: ["id"]
    }
                  ]
                },"rule_definitions": {
                  Row: {
                    "active": boolean,"category": string,"code": string,"created_at": string,"description": string,"severity_hint": string,"version": string
                  }
                  ComputedFields: never
                  Insert: {
                    "active"?: boolean,"category": string,"code": string,"created_at"?: string,"description": string,"severity_hint": string,"version": string
                  }
                  Update: {
                    "active"?: boolean,"category"?: string,"code"?: string,"created_at"?: string,"description"?: string,"severity_hint"?: string,"version"?: string
                  }
                  Relationships: [

                  ]
                },"rule_matches": {
                  Row: {
                    "created_at": string,"details": NonNullable<Json>,"execution_id": string,"id": string,"matched_event_ids": (string)[],"rule_code": string,"rule_version": string,"tenant_id": string,"updated_at": string
                  }
                  ComputedFields: never
                  Insert: {
                    "created_at"?: string,"details"?: NonNullable<Json>,"execution_id": string,"id"?: string,"matched_event_ids": (string)[],"rule_code": string,"rule_version": string,"tenant_id": string,"updated_at"?: string
                  }
                  Update: {
                    "created_at"?: string,"details"?: NonNullable<Json>,"execution_id"?: string,"id"?: string,"matched_event_ids"?: (string)[],"rule_code"?: string,"rule_version"?: string,"tenant_id"?: string,"updated_at"?: string
                  }
                  Relationships: [
                    {
      foreignKeyName: "rule_matches_rule_code_rule_version_fkey"
      columns: ["rule_code","rule_version"]
isOneToOne: false
      referencedRelation: "rule_definitions"
      referencedColumns: ["code","version"]
    },{
      foreignKeyName: "rule_matches_tenant_id_execution_id_fkey"
      columns: ["tenant_id","execution_id"]
isOneToOne: false
      referencedRelation: "executions"
      referencedColumns: ["tenant_id","id"]
    },{
      foreignKeyName: "rule_matches_tenant_id_fkey"
      columns: ["tenant_id"]
isOneToOne: false
      referencedRelation: "tenants"
      referencedColumns: ["id"]
    }
                  ]
                },"schema_migrations": {
                  Row: {
                    "applied_at": string,"version": string
                  }
                  ComputedFields: never
                  Insert: {
                    "applied_at"?: string,"version": string
                  }
                  Update: {
                    "applied_at"?: string,"version"?: string
                  }
                  Relationships: [

                  ]
                },"tenants": {
                  Row: {
                    "ai_profile": string,"ai_project": string | null,"auto_diagnose_critical": boolean,"created_at": string,"deletion_requested_at": string | null,"deletion_requested_by": string | null,"deletion_scheduled_for": string | null,"dpa_accepted_at": string | null,"id": string,"llm_enabled": boolean,"llm_provider": string,"mttr_baseline_minutes": number | null,"plan": string,"quota_tolerance": number,"segment": string | null,"status": string,"updated_at": string
                  }
                  ComputedFields: never
                  Insert: {
                    "ai_profile"?: string,"ai_project"?: string | null,"auto_diagnose_critical"?: boolean,"created_at"?: string,"deletion_requested_at"?: string | null,"deletion_requested_by"?: string | null,"deletion_scheduled_for"?: string | null,"dpa_accepted_at"?: string | null,"id": string,"llm_enabled"?: boolean,"llm_provider"?: string,"mttr_baseline_minutes"?: number | null,"plan"?: string,"quota_tolerance"?: number,"segment"?: string | null,"status"?: string,"updated_at"?: string
                  }
                  Update: {
                    "ai_profile"?: string,"ai_project"?: string | null,"auto_diagnose_critical"?: boolean,"created_at"?: string,"deletion_requested_at"?: string | null,"deletion_requested_by"?: string | null,"deletion_scheduled_for"?: string | null,"dpa_accepted_at"?: string | null,"id"?: string,"llm_enabled"?: boolean,"llm_provider"?: string,"mttr_baseline_minutes"?: number | null,"plan"?: string,"quota_tolerance"?: number,"segment"?: string | null,"status"?: string,"updated_at"?: string
                  }
                  Relationships: [

                  ]
                },"usage_alerts": {
                  Row: {
                    "created_at": string,"id": string,"period_start": string,"resource": string,"tenant_id": string,"threshold": number,"updated_at": string
                  }
                  ComputedFields: never
                  Insert: {
                    "created_at"?: string,"id"?: string,"period_start": string,"resource": string,"tenant_id": string,"threshold": number,"updated_at"?: string
                  }
                  Update: {
                    "created_at"?: string,"id"?: string,"period_start"?: string,"resource"?: string,"tenant_id"?: string,"threshold"?: number,"updated_at"?: string
                  }
                  Relationships: [
                    {
      foreignKeyName: "usage_alerts_tenant_id_fkey"
      columns: ["tenant_id"]
isOneToOne: false
      referencedRelation: "tenants"
      referencedColumns: ["id"]
    }
                  ]
                },"usage_deltas": {
                  Row: {
                    "amount": number,"created_at": string,"id": number,"period_start": string,"resource": string,"tenant_id": string
                  }
                  ComputedFields: never
                  Insert: {
                    "amount": number,"created_at"?: string,"id"?: never,"period_start": string,"resource": string,"tenant_id": string
                  }
                  Update: {
                    "amount"?: number,"created_at"?: string,"id"?: never,"period_start"?: string,"resource"?: string,"tenant_id"?: string
                  }
                  Relationships: [
                    {
      foreignKeyName: "usage_deltas_tenant_id_fkey"
      columns: ["tenant_id"]
isOneToOne: false
      referencedRelation: "tenants"
      referencedColumns: ["id"]
    }
                  ]
                },"usage_llm": {
                  Row: {
                    "cost_estimate": number | null,"created_at": string,"diagnosis_id": string | null,"id": string,"input_tokens": number,"model": string | null,"output_tokens": number,"provider": string,"tenant_id": string,"updated_at": string
                  }
                  ComputedFields: never
                  Insert: {
                    "cost_estimate"?: number | null,"created_at"?: string,"diagnosis_id"?: string | null,"id"?: string,"input_tokens"?: number,"model"?: string | null,"output_tokens"?: number,"provider": string,"tenant_id": string,"updated_at"?: string
                  }
                  Update: {
                    "cost_estimate"?: number | null,"created_at"?: string,"diagnosis_id"?: string | null,"id"?: string,"input_tokens"?: number,"model"?: string | null,"output_tokens"?: number,"provider"?: string,"tenant_id"?: string,"updated_at"?: string
                  }
                  Relationships: [
                    {
      foreignKeyName: "usage_llm_tenant_id_diagnosis_id_fkey"
      columns: ["tenant_id","diagnosis_id"]
isOneToOne: false
      referencedRelation: "diagnoses"
      referencedColumns: ["tenant_id","id"]
    },{
      foreignKeyName: "usage_llm_tenant_id_fkey"
      columns: ["tenant_id"]
isOneToOne: false
      referencedRelation: "tenants"
      referencedColumns: ["id"]
    }
                  ]
                },"usage_records": {
                  Row: {
                    "created_at": string,"id": string,"period_start": string,"quantity": number,"resource": string,"tenant_id": string,"updated_at": string
                  }
                  ComputedFields: never
                  Insert: {
                    "created_at"?: string,"id"?: string,"period_start": string,"quantity"?: number,"resource": string,"tenant_id": string,"updated_at"?: string
                  }
                  Update: {
                    "created_at"?: string,"id"?: string,"period_start"?: string,"quantity"?: number,"resource"?: string,"tenant_id"?: string,"updated_at"?: string
                  }
                  Relationships: [
                    {
      foreignKeyName: "usage_records_tenant_id_fkey"
      columns: ["tenant_id"]
isOneToOne: false
      referencedRelation: "tenants"
      referencedColumns: ["id"]
    }
                  ]
                },"user_active_tenant": {
                  Row: {
                    "tenant_id": string,"updated_at": string,"user_id": string
                  }
                  ComputedFields: never
                  Insert: {
                    "tenant_id": string,"updated_at"?: string,"user_id": string
                  }
                  Update: {
                    "tenant_id"?: string,"updated_at"?: string,"user_id"?: string
                  }
                  Relationships: [
                    {
      foreignKeyName: "user_active_tenant_tenant_id_user_id_fkey"
      columns: ["tenant_id","user_id"]
isOneToOne: false
      referencedRelation: "memberships"
      referencedColumns: ["tenant_id","user_id"]
    }
                  ]
                },"webhook_deliveries": {
                  Row: {
                    "attempts": number,"body": Json | null,"created_at": string,"delivered_at": string | null,"error": string | null,"event": string,"id": string,"latency_ms": number | null,"next_attempt_at": string | null,"resent_from": string | null,"response_excerpt": string | null,"response_status": number | null,"status": string,"subject": NonNullable<Json>,"tenant_id": string,"updated_at": string,"webhook_id": string
                  }
                  ComputedFields: never
                  Insert: {
                    "attempts"?: number,"body"?: Json | null,"created_at"?: string,"delivered_at"?: string | null,"error"?: string | null,"event": string,"id"?: string,"latency_ms"?: number | null,"next_attempt_at"?: string | null,"resent_from"?: string | null,"response_excerpt"?: string | null,"response_status"?: number | null,"status"?: string,"subject": NonNullable<Json>,"tenant_id": string,"updated_at"?: string,"webhook_id": string
                  }
                  Update: {
                    "attempts"?: number,"body"?: Json | null,"created_at"?: string,"delivered_at"?: string | null,"error"?: string | null,"event"?: string,"id"?: string,"latency_ms"?: number | null,"next_attempt_at"?: string | null,"resent_from"?: string | null,"response_excerpt"?: string | null,"response_status"?: number | null,"status"?: string,"subject"?: NonNullable<Json>,"tenant_id"?: string,"updated_at"?: string,"webhook_id"?: string
                  }
                  Relationships: [
                    {
      foreignKeyName: "webhook_deliveries_tenant_id_fkey"
      columns: ["tenant_id"]
isOneToOne: false
      referencedRelation: "tenants"
      referencedColumns: ["id"]
    },{
      foreignKeyName: "webhook_deliveries_tenant_id_resent_from_fkey"
      columns: ["tenant_id","resent_from"]
isOneToOne: false
      referencedRelation: "webhook_deliveries"
      referencedColumns: ["tenant_id","id"]
    },{
      foreignKeyName: "webhook_deliveries_tenant_id_webhook_id_fkey"
      columns: ["tenant_id","webhook_id"]
isOneToOne: false
      referencedRelation: "webhooks"
      referencedColumns: ["tenant_id","id"]
    }
                  ]
                },"webhooks": {
                  Row: {
                    "created_at": string,"created_by": string | null,"disabled_reason": string | null,"enabled": boolean,"events": (string)[],"failure_count": number,"id": string,"last_delivery_at": string | null,"last_status": number | null,"name": string,"secret_id": string,"tenant_id": string,"updated_at": string,"url": string
                  }
                  ComputedFields: never
                  Insert: {
                    "created_at"?: string,"created_by"?: string | null,"disabled_reason"?: string | null,"enabled"?: boolean,"events": (string)[],"failure_count"?: number,"id"?: string,"last_delivery_at"?: string | null,"last_status"?: number | null,"name": string,"secret_id": string,"tenant_id": string,"updated_at"?: string,"url": string
                  }
                  Update: {
                    "created_at"?: string,"created_by"?: string | null,"disabled_reason"?: string | null,"enabled"?: boolean,"events"?: (string)[],"failure_count"?: number,"id"?: string,"last_delivery_at"?: string | null,"last_status"?: number | null,"name"?: string,"secret_id"?: string,"tenant_id"?: string,"updated_at"?: string,"url"?: string
                  }
                  Relationships: [
                    {
      foreignKeyName: "webhooks_tenant_id_fkey"
      columns: ["tenant_id"]
isOneToOne: false
      referencedRelation: "tenants"
      referencedColumns: ["id"]
    }
                  ]
                }
          }
          Views: {
            [_ in never]: never
          }
          Functions: {
            "accept_agent_batch":
{ Args: { "events": Json,"secret_hash": string }; Returns: string
                           },
"accept_ingestion_batch":
{ Args: { "events": Json,"token_hash": string }; Returns: string
                           },
"accept_invitation":
{ Args: { "token_hash": string }; Returns: string
                           },
"active_report_share":
{ Args: { "token_hash": string }; Returns: {
              "access_count": number,
"created_at": string,
"created_by": string | null,
"download_url": string,
"expires_at": string,
"id": string,
"last_accessed_at": string | null,
"report_id": string,
"revoked_at": string | null,
"revoked_by": string | null,
"tenant_id": string,
"token_hash": string,
"updated_at": string
            }
                          SetofOptions: {
        from: "*"
        to: "report_shares"
        isOneToOne: true
        isSetofReturn: false
      } },
"add_incident_comment":
{ Args: { "body": string,"mentioned": (string)[],"target": string }; Returns: string
                           },
"agent_seen":
{ Args: { "secret_hash": string,"version": string }; Returns: undefined
                           },
"ai_profile_status":
{ Args: Record<PropertyKey, never>; Returns: {
              "checked_at": string,"detail": string,"hosts": (string)[],"in_region": boolean,"ok": boolean,"profile": string,"region": string
            }[]
                           },
"alert_audience":
{ Args: { "everyone": boolean,"tenant": string }; Returns: {
              "email": string,"quiet_hours": Json,"user_id": string
            }[]
                           },
"cancel_tenant_deletion":
{ Args: Record<PropertyKey, never>; Returns: undefined
                           },
"claim_local_llm":
{ Args: { "secret_hash": string }; Returns: {
              "id": string,"request": Json,"timeout_seconds": number
            }[]
                           },
"claim_push_endpoint":
{ Args: { "endpoint": string }; Returns: undefined
                           },
"comment_author_name":
{ Args: { "target": string }; Returns: string
                           },
"configure_jira":
{ Args: { "cloud_id": string,"custom_fields": Json,"hook_token": string,"issue_type": string,"priority_map": Json,"project_key": string,"sync_status": boolean }; Returns: undefined
                           },
"configure_servicenow":
{ Args: { "assignment_groups": Json,"client_id": string,"client_secret": string,"default_group": string,"hook_token": string,"impact_map": Json,"instance_url": string,"sync_status": boolean }; Returns: string
                           },
"create_agent":
{ Args: { "config": Json,"integration_id": string,"name": string,"token_hash": string }; Returns: string
                           },
"create_connector":
{ Args: { "config": Json,"integration_id": string,"name": string,"provider": string,"secret": string,"sync_interval_seconds"?: number }; Returns: string
                           },
"create_import":
{ Args: { "filename": string,"integration_id": string,"sha256": string,"size_bytes": number }; Returns: {
              "duplicate_of": string,"error": string,"format": string,"id": string,"status": string
            }[]
                           },
"create_ingestion_token":
{ Args: { "integration_id": string,"name": string,"prefix": string,"token_hash": string }; Returns: string
                           },
"create_knowledge_document":
{ Args: { "content_type": string,"filename": string,"size_bytes": number,"title": string }; Returns: {
              "id": string,"storage_path": string
            }[]
                           },
"create_notification_channel":
{ Args: { "config": Json,"name": string,"secret": string,"type": string }; Returns: string
                           },
"create_organization":
{ Args: { "llm_provider": string,"name": string,"segment": string,"slug": string }; Returns: string
                           },
"create_report_share":
{ Args: { "download_url": string,"report": string,"token_hash": string }; Returns: {
              "expires_at": string,"id": string
            }[]
                           },
"create_webhook":
{ Args: { "events": (string)[],"name": string,"secret": string,"url": string }; Returns: string
                           },
"current_aal":
{ Args: Record<PropertyKey, never>; Returns: string
                           },
"current_tenant_id":
{ Args: Record<PropertyKey, never>; Returns: string
                           },
"current_tenant_role":
{ Args: Record<PropertyKey, never>; Returns: string
                           },
"current_usage":
{ Args: { "resource": string,"tenant": string }; Returns: number
                           },
"custom_access_token_hook":
{ Args: { "event": Json }; Returns: Json
                           },
"delete_knowledge_document":
{ Args: { "target": string }; Returns: string
                           },
"delete_notification_channel":
{ Args: { "target": string }; Returns: undefined
                           },
"delete_webhook":
{ Args: { "target": string }; Returns: undefined
                           },
"diagnosis_is_final":
{ Args: { "status": string }; Returns: boolean
                           },
"diagnosis_snapshot":
{ Args: { "target": string }; Returns: Json
                           },
"disconnect_jira":
{ Args: Record<PropertyKey, never>; Returns: undefined
                           },
"disconnect_servicenow":
{ Args: Record<PropertyKey, never>; Returns: undefined
                           },
"drop_expired_partitions":
{ Args: Record<PropertyKey, never>; Returns: (string)[]
                           },
"due_tenant_deletions":
{ Args: Record<PropertyKey, never>; Returns: {
              "tenant_id": string
            }[]
                           },
"effective_retention":
{ Args: { "data_class": string,"tenant": string }; Returns: number
                           },
"ensure_audit_partition":
{ Args: { "day": string }; Returns: string
                           },
"ensure_event_partition":
{ Args: { "day": string }; Returns: string
                           },
"erase_subject_events":
{ Args: { "reference": string }; Returns: number
                           },
"expired_raw_logs":
{ Args: { "batch": number }; Returns: {
              "id": string,"storage_path": string,"tenant_id": string
            }[]
                           },
"find_subject_events":
{ Args: { "reference": string }; Returns: {
              "events": number,"first_seen": string,"last_seen": string
            }[]
                           },
"finish_import":
{ Args: { "reason": string,"stored_size": number,"target": string }; Returns: undefined
                           },
"finish_itsm_oauth":
{ Args: { "sites": Json,"state_hash": string,"tokens": string }; Returns: string
                           },
"finish_knowledge_upload":
{ Args: { "target": string }; Returns: undefined
                           },
"finish_local_llm":
{ Args: { "error": string,"request_id": string,"response": Json,"secret_hash": string }; Returns: boolean
                           },
"finish_report":
{ Args: { "digest": string,"path": string,"report": string,"size": number }; Returns: undefined
                           },
"forget_raw_logs":
{ Args: { "targets": (string)[] }; Returns: number
                           },
"freeze_tenant":
{ Args: { "tenant": string }; Returns: undefined
                           },
"get_channel_secret":
{ Args: { "target": string }; Returns: string
                           },
"get_connector_secret":
{ Args: { "target": string }; Returns: string
                           },
"get_itsm_tokens":
{ Args: { "target": string }; Returns: string
                           },
"get_webhook_secret":
{ Args: { "target": string }; Returns: string
                           },
"has_alert_rules":
{ Args: { "kind": string,"tenant": string }; Returns: boolean
                           },
"has_member_role":
{ Args: { "roles": (string)[] }; Returns: boolean
                           },
"has_role":
{ Args: { "roles": (string)[] }; Returns: boolean
                           },
"import_auth_events":
{ Args: { "since": string }; Returns: number
                           },
"import_storage_path":
{ Args: { "format": string,"import_id": string,"tenant": string }; Returns: string
                           },
"imported_before":
{ Args: { "integration": string,"sha": string,"tenant": string }; Returns: string
                           },
"incident_snapshot":
{ Args: { "incident": Omit<Database["doctor"]['Tables']["incidents"]['Row'], Database["doctor"]['Tables']["incidents"]['ComputedFields']> }; Returns: Json
                           },
"increment_usage":
{ Args: { "amount": number,"resource": string,"tenant": string }; Returns: number
                           },
"ingestion_over_quota":
{ Args: { "pending": number,"tenant": string }; Returns: boolean
                           },
"invite_member":
{ Args: { "email": string,"role": string,"token_hash": string }; Returns: {
              "id": string,"organization": string
            }[]
                           },
"is_manager":
{ Args: Record<PropertyKey, never>; Returns: boolean
                           },
"jira_hook":
{ Args: { "issue_key": string,"token_hash": string }; Returns: boolean
                           },
"list_audit_actors":
{ Args: Record<PropertyKey, never>; Returns: {
              "email": string,"user_id": string
            }[]
                           },
"list_invitations":
{ Args: Record<PropertyKey, never>; Returns: {
              "email": string,"expires_at": string,"id": string,"role": string
            }[]
                           },
"list_members":
{ Args: Record<PropertyKey, never>; Returns: {
              "display_name": string,"email": string,"id": string,"mfa_enabled": boolean,"role": string
            }[]
                           },
"list_organizations":
{ Args: Record<PropertyKey, never>; Returns: {
              "id": string,"name": string,"role": string,"slug": string
            }[]
                           },
"lock_audit_partition":
{ Args: { "partition_name": string }; Returns: undefined
                           },
"locked_target":
{ Args: { "actor_role": string,"target": string }; Returns: {
              "created_at": string,
"id": string,
"role": string,
"tenant_id": string,
"updated_at": string,
"user_id": string
            }
                          SetofOptions: {
        from: "*"
        to: "memberships"
        isOneToOne: true
        isSetofReturn: false
      } },
"managed_connector":
{ Args: { "target": string }; Returns: {
              "checkpoint": Json | null,
"config": NonNullable<Json>,
"config_version": number,
"consecutive_failures": number,
"created_at": string,
"created_by": string | null,
"id": string,
"integration_id": string,
"last_error": string | null,
"last_sync_at": string | null,
"name": string,
"next_run_at": string,
"paused_reason": string | null,
"provider": string,
"secret_id": string | null,
"status": string,
"sync_interval_seconds": number,
"tenant_id": string,
"updated_at": string
            }
                          SetofOptions: {
        from: "*"
        to: "connectors"
        isOneToOne: true
        isSetofReturn: false
      } },
"my_retention":
{ Args: { "data_class": string }; Returns: number
                           },
"my_usage":
{ Args: Record<PropertyKey, never>; Returns: {
              "period": string,"quota": number,"resource": string,"used": number
            }[]
                           },
"open_report_share":
{ Args: { "token_hash": string }; Returns: {
              "download_url": string,"filename": string,"format": string
            }[]
                           },
"pause_connector":
{ Args: { "target": string }; Returns: undefined
                           },
"plan_limit":
{ Args: { "resource": string,"tenant": string }; Returns: number
                           },
"platform_health":
{ Args: Record<PropertyKey, never>; Returns: Json
                           },
"promote_incident_to_knowledge":
{ Args: { "incident": string }; Returns: string
                           },
"purge_tenant":
{ Args: { "storage_objects": number,"tenant": string }; Returns: string
                           },
"purge_tenant_data":
{ Args: { "raw_logs"?: number,"tenant": string }; Returns: Json
                           },
"put_connector_secret":
{ Args: { "secret": string,"target": string }; Returns: undefined
                           },
"put_itsm_tokens":
{ Args: { "target": string,"tokens": string }; Returns: undefined
                           },
"queue_ticket":
{ Args: { "incident": string,"provider"?: string,"requester": string,"rule": string,"tenant": string }; Returns: string
                           },
"queue_webhooks":
{ Args: { "event": string,"subject": Json,"tenant": string }; Returns: undefined
                           },
"quota_recipients":
{ Args: { "tenant": string }; Returns: {
              "email": string,"organization": string
            }[]
                           },
"record_audit":
{ Args: { "action": string,"target": string,"tenant": string }; Returns: undefined
                           },
"record_audit_export":
{ Args: { "filters": Json }; Returns: undefined
                           },
"record_report_share_access":
{ Args: { "token_hash": string }; Returns: undefined
                           },
"refresh_execution_stats":
{ Args: { "batch"?: number }; Returns: number
                           },
"register_agent":
{ Args: { "fingerprint": string,"public_key": string,"secret_hash": string,"token_hash": string,"version": string }; Returns: {
              "agent_id": string,"integration_id": string,"tenant_id": string
            }[]
                           },
"remove_member":
{ Args: { "target": string }; Returns: undefined
                           },
"report_reviews":
{ Args: { "diagnosis": string,"tenant": string }; Returns: {
              "comment": string,"created_at": string,"reviewer": string,"verdict": string
            }[]
                           },
"request_connector_sync":
{ Args: { "target": string }; Returns: undefined
                           },
"request_diagnosis":
{ Args: { "incident": string,"include_knowledge_base": boolean,"processing_key": string,"requested_mode": string }; Returns: {
              "created": boolean,"id": string,"status": string,"version": number
            }[]
                           },
"request_raw_log_download":
{ Args: { "target": string }; Returns: string
                           },
"request_report":
{ Args: { "format": string,"incident": string,"include_event_excerpts": boolean,"include_timeline": boolean,"processing_key": string }; Returns: {
              "created": boolean,"id": string,"status": string
            }[]
                           },
"request_tenant_deletion":
{ Args: { "confirmation": string }; Returns: string
                           },
"request_ticket":
{ Args: { "provider"?: string,"target": string }; Returns: string
                           },
"require_manager":
{ Args: Record<PropertyKey, never>; Returns: string
                           },
"require_other_owner":
{ Args: { "membership": Omit<Database["doctor"]['Tables']["memberships"]['Row'], Database["doctor"]['Tables']["memberships"]['ComputedFields']> }; Returns: undefined
                           },
"resend_invitation":
{ Args: { "target": string,"token_hash": string }; Returns: {
              "email": string,"organization": string
            }[]
                           },
"resend_webhook_delivery":
{ Args: { "target": string }; Returns: string
                           },
"reserve_llm_quota":
{ Args: { "diagnosis": string,"provider": string,"tenant": string }; Returns: boolean
                           },
"resolve_agent":
{ Args: { "secret_hash": string }; Returns: {
              "agent_id": string,"config": Json,"config_version": number,"integration_id": string,"public_key": string,"tenant_id": string
            }[]
                           },
"resolve_ingestion_token":
{ Args: { "token_hash": string }; Returns: {
              "integration_id": string,"tenant_id": string,"token_id": string
            }[]
                           },
"resume_connector":
{ Args: { "target": string }; Returns: undefined
                           },
"retention_bounds":
{ Args: { "data_class": string }; Returns: {
              "default_days": number,"max_days": number,"min_days": number
            }[]
                           },
"revoke_agent":
{ Args: { "target": string }; Returns: undefined
                           },
"revoke_ingestion_token":
{ Args: { "target": string }; Returns: undefined
                           },
"revoke_invitation":
{ Args: { "target": string }; Returns: undefined
                           },
"revoke_report_share":
{ Args: { "share": string }; Returns: undefined
                           },
"rollup_usage":
{ Args: Record<PropertyKey, never>; Returns: number
                           },
"rotate_agent":
{ Args: { "target": string,"token_hash": string }; Returns: undefined
                           },
"rotate_webhook_secret":
{ Args: { "secret": string,"target": string }; Returns: undefined
                           },
"servicenow_hook":
{ Args: { "number": string,"token_hash": string }; Returns: boolean
                           },
"set_ai_profile":
{ Args: { "profile": string }; Returns: undefined
                           },
"set_auto_diagnosis":
{ Args: { "enabled": boolean }; Returns: undefined
                           },
"set_dedicated_ai":
{ Args: { "project": string,"tenant": string }; Returns: undefined
                           },
"set_llm_enabled":
{ Args: { "enabled": boolean }; Returns: undefined
                           },
"set_local_ai":
{ Args: { "agent": string,"endpoint_url": string,"model": string,"tenant": string,"timeout_seconds": number,"transport": string }; Returns: undefined
                           },
"set_retention_policy":
{ Args: { "data_class": string,"days": number }; Returns: undefined
                           },
"set_usage":
{ Args: { "resource": string,"tenant": string,"value": number }; Returns: undefined
                           },
"start_itsm_oauth":
{ Args: { "state_hash": string }; Returns: undefined
                           },
"submit_diagnosis_feedback":
{ Args: { "comment": string,"correct_category": string,"correct_cause": string,"responsible_system": string,"target": string,"verdict": string }; Returns: {
              "comment": string | null,
"correct_category": string | null,
"correct_cause": string | null,
"created_at": string,
"diagnosis_id": string,
"id": string,
"responsible_system": string | null,
"reviewer_id": string | null,
"tenant_id": string,
"time_to_review_s": number | null,
"updated_at": string,
"verdict": string
            }
                          SetofOptions: {
        from: "*"
        to: "diagnosis_feedback"
        isOneToOne: true
        isSetofReturn: false
      } },
"switch_organization":
{ Args: { "target": string }; Returns: undefined
                           },
"update_agent_config":
{ Args: { "config": Json,"target": string }; Returns: number
                           },
"update_connector":
{ Args: { "config": Json,"name": string,"sync_interval_seconds": number,"target": string }; Returns: undefined
                           },
"update_incident":
{ Args: { "new_assignee": string,"new_severity": string,"new_status": string,"note": string,"set_assignee": boolean,"target": string }; Returns: undefined
                           },
"update_member_role":
{ Args: { "role": string,"target": string }; Returns: undefined
                           },
"update_webhook":
{ Args: { "enabled": boolean,"events": (string)[],"target": string,"url": string }; Returns: undefined
                           },
"usage_period":
{ Args: { "at"?: string,"resource": string }; Returns: string
                           },
"usage_thresholds":
{ Args: { "after": number,"before": number,"resource": string,"tenant": string }; Returns: undefined
                           },
"utc_hour":
{ Args: { "moment": string }; Returns: string
                           },
"write_audit":
{ Args: { "action": string,"after": Json,"before": Json,"resource_id": string,"resource_type": string,"tenant": string }; Returns: undefined
                           }
          }
          Enums: {
            [_ in never]: never
          }
          CompositeTypes: {
            [_ in never]: never
          }
        }
}

type DatabaseWithoutInternals = Omit<Database, '__InternalSupabase'>

type DefaultSchema = DatabaseWithoutInternals[Extract<keyof Database, "doctor">]

export type Tables<
  DefaultSchemaTableNameOrOptions extends
    | keyof (DefaultSchema["Tables"] & DefaultSchema["Views"])
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
        DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])
    : never = never
> = DefaultSchemaTableNameOrOptions extends { schema: keyof DatabaseWithoutInternals }
  ? (DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"] &
      DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Views"])[TableName] extends {
      Row: infer R
    }
    ? R
    : never
  : DefaultSchemaTableNameOrOptions extends keyof (DefaultSchema["Tables"] & DefaultSchema["Views"])
  ? (DefaultSchema["Tables"] & DefaultSchema["Views"])[DefaultSchemaTableNameOrOptions] extends {
      Row: infer R
    }
    ? R
    : never
  : never

export type TablesInsert<
  DefaultSchemaTableNameOrOptions extends
    | keyof DefaultSchema["Tables"]
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never = never
> = DefaultSchemaTableNameOrOptions extends { schema: keyof DatabaseWithoutInternals }
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Insert: infer I
    }
    ? I
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
  ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
      Insert: infer I
    }
    ? I
    : never
  : never

export type TablesUpdate<
  DefaultSchemaTableNameOrOptions extends
    | keyof DefaultSchema["Tables"]
    | { schema: keyof DatabaseWithoutInternals },
  TableName extends DefaultSchemaTableNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"]
    : never = never
> = DefaultSchemaTableNameOrOptions extends { schema: keyof DatabaseWithoutInternals }
  ? DatabaseWithoutInternals[DefaultSchemaTableNameOrOptions["schema"]]["Tables"][TableName] extends {
      Update: infer U
    }
    ? U
    : never
  : DefaultSchemaTableNameOrOptions extends keyof DefaultSchema["Tables"]
  ? DefaultSchema["Tables"][DefaultSchemaTableNameOrOptions] extends {
      Update: infer U
    }
    ? U
    : never
  : never

export type Enums<
  DefaultSchemaEnumNameOrOptions extends
    | keyof DefaultSchema["Enums"]
    | { schema: keyof DatabaseWithoutInternals },
  EnumName extends DefaultSchemaEnumNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"]
    : never = never
> = DefaultSchemaEnumNameOrOptions extends { schema: keyof DatabaseWithoutInternals }
  ? DatabaseWithoutInternals[DefaultSchemaEnumNameOrOptions["schema"]]["Enums"][EnumName]
  : DefaultSchemaEnumNameOrOptions extends keyof DefaultSchema["Enums"]
  ? DefaultSchema["Enums"][DefaultSchemaEnumNameOrOptions]
  : never

export type CompositeTypes<
  PublicCompositeTypeNameOrOptions extends
    | keyof DefaultSchema["CompositeTypes"]
    | { schema: keyof DatabaseWithoutInternals },
  CompositeTypeName extends PublicCompositeTypeNameOrOptions extends {
    schema: keyof DatabaseWithoutInternals
  }
    ? keyof DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"]
    : never = never
> = PublicCompositeTypeNameOrOptions extends { schema: keyof DatabaseWithoutInternals }
  ? DatabaseWithoutInternals[PublicCompositeTypeNameOrOptions["schema"]]["CompositeTypes"][CompositeTypeName]
  : PublicCompositeTypeNameOrOptions extends keyof DefaultSchema["CompositeTypes"]
  ? DefaultSchema["CompositeTypes"][PublicCompositeTypeNameOrOptions]
  : never

export const Constants = {
  "doctor": {
          Enums: {

          }
        }
} as const
