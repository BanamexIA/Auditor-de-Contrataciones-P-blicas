"""Usuarios en memoria para pruebas."""

from datetime import datetime, timezone

from backend.usuarios.repositorio import (
    UsuarioDuplicado,
    UsuarioNoEncontrado,
    validar_email,
    validar_rol,
    validar_usuario,
)
from backend.usuarios.seguridad import hashear

SECRETO = "s" * 40


class RepositorioUsuariosEnMemoria:
    def __init__(self):
        self.usuarios = {}

    def _publico(self, u):
        return {k: v for k, v in u.items() if k != "hash_contrasena"}

    def alta(self, usuario, nombre, rol, contrasena, email=None):
        usuario, rol, email = validar_usuario(usuario), validar_rol(rol), validar_email(email)
        if usuario in self.usuarios and self.usuarios[usuario]["activo"]:
            raise UsuarioDuplicado(usuario)
        self.usuarios[usuario] = {"id": len(self.usuarios) + 1, "usuario": usuario,
                                  "nombre": nombre, "rol": rol, "email": email, "activo": True,
                                  "hash_contrasena": hashear(contrasena),
                                  "created_at": datetime.now(timezone.utc), "ultimo_acceso": None}
        return self._publico(self.usuarios[usuario])

    def _existente(self, usuario):
        u = self.usuarios.get(validar_usuario(usuario))
        if u is None:
            raise UsuarioNoEncontrado(usuario)
        return u

    def baja(self, usuario):
        u = self._existente(usuario)
        u["activo"] = False
        return self._publico(u)

    def cambiar_rol(self, usuario, rol):
        u = self._existente(usuario)
        u["rol"] = validar_rol(rol)
        return self._publico(u)

    def cambiar_contrasena(self, usuario, contrasena):
        u = self._existente(usuario)
        u["hash_contrasena"] = hashear(contrasena)
        return self._publico(u)

    def listar(self, incluir_inactivos=False):
        return [self._publico(u) for _, u in sorted(self.usuarios.items())
                if incluir_inactivos or u["activo"]]

    def credenciales(self, usuario):
        u = self.usuarios.get((usuario or "").strip().lower())
        return dict(u) if u and u["activo"] else None

    def activo(self, usuario):
        u = self.usuarios.get(usuario)
        return self._publico(u) if u and u["activo"] else None

    def activo_por_email(self, email):
        email = (email or "").strip().lower()
        for u in self.usuarios.values():
            if u["activo"] and u.get("email") == email:
                return self._publico(u)
        return None

    def cambiar_email(self, usuario, email):
        u = self._existente(usuario)
        email = validar_email(email)
        if email and any(o.get("email") == email and o is not u for o in self.usuarios.values()):
            raise ValueError("Ese correo ya está asignado a otro usuario.")
        u["email"] = email
        return self._publico(u)

    def registrar_acceso(self, usuario):
        self.usuarios[usuario]["ultimo_acceso"] = datetime.now(timezone.utc)
