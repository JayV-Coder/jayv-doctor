"""Matriz de permissões do ticket #6: quem faz o quê. O RLS repete a regra com `doctor.has_role`."""

VIEW = ("owner", "admin", "analyst", "viewer")
OPERATE = ("owner", "admin", "analyst")
IMPORT_LOGS = ("owner", "admin", "analyst")
MANAGE_CONNECTORS = ("owner", "admin")
MANAGE_MEMBERS = ("owner", "admin")
GOVERN = ("owner",)
