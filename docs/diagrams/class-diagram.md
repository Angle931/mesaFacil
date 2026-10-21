# Diagrama de clases del dominio

Este diagrama representa el diseño conceptual de MesaFácil.

La clase `Administrador` representa al usuario administrativo proporcionado
por Django Authentication y Django Admin. No corresponde a un modelo propio
del dominio.

```mermaid
classDiagram
    class Cliente {
        -String nombre
        -String telefono
        -String correoOpcional
        +proporcionarDatos()
        +actualizarDatos()
    }

    class Reserva {
        -String codigoConfirmacion
        -Date fecha
        -Time hora
        -int cantidadPersonas
        -String estado
        +registrar()
        +modificar()
        +actualizarEstado(nuevoEstado)
        +generarCodigoConfirmacion()
    }

    class Mesa {
        -int numero
        -int capacidad
        -Boolean activa
        +verificarDisponibilidad(fecha, hora) boolean
        +actualizarDatos()
        +actualizarEstado(nuevoEstado)
    }

    class Administrador {
        -String usuario
        -String contrasena
        +autenticar(usuario, contrasena) boolean
        +consultarReservas()
        +modificarReserva()
        +gestionarMesas()
    }

    Cliente "1" --> "0..*" Reserva : realiza
    Reserva "0..*" --> "1" Mesa : se asigna a

    Administrador ..> Reserva : gestiona
    Administrador ..> Mesa : administra
```