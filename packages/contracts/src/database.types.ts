
export type Json = string | number | boolean | null | { [key: string]: Json | undefined } | Json[]

export type Database = {

  "doctor": {
          Tables: {
            "idempotency_keys": {
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
                    "created_at": string,"dpa_accepted_at": string | null,"id": string,"llm_provider": string,"plan": string,"segment": string | null,"status": string,"updated_at": string
                  }
                  ComputedFields: never
                  Insert: {
                    "created_at"?: string,"dpa_accepted_at"?: string | null,"id": string,"llm_provider"?: string,"plan"?: string,"segment"?: string | null,"status"?: string,"updated_at"?: string
                  }
                  Update: {
                    "created_at"?: string,"dpa_accepted_at"?: string | null,"id"?: string,"llm_provider"?: string,"plan"?: string,"segment"?: string | null,"status"?: string,"updated_at"?: string
                  }
                  Relationships: [

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
                }
          }
          Views: {
            [_ in never]: never
          }
          Functions: {
            "accept_invitation":
{ Args: { "token_hash": string }; Returns: string
                           },
"create_organization":
{ Args: { "llm_provider": string,"name": string,"segment": string,"slug": string }; Returns: string
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
"custom_access_token_hook":
{ Args: { "event": Json }; Returns: Json
                           },
"has_role":
{ Args: { "roles": (string)[] }; Returns: boolean
                           },
"invite_member":
{ Args: { "email": string,"role": string,"token_hash": string }; Returns: {
              "id": string,"organization": string
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
"remove_member":
{ Args: { "target": string }; Returns: undefined
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
"revoke_invitation":
{ Args: { "target": string }; Returns: undefined
                           },
"switch_organization":
{ Args: { "target": string }; Returns: undefined
                           },
"update_member_role":
{ Args: { "role": string,"target": string }; Returns: undefined
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
