# Operación del laboratorio

## Antes de iniciar

Ejecutar los tests, revisar `configs/lab.json`, crear `.env` mediante `trading-lab init` y verificar acceso a datos públicos. El panel es local; no se incluye exposición a Internet. La aplicación no necesita claves de trading.

La imagen Docker usa `ftuser`. Si el volumen no admite escritura en Linux, comprobar el UID del usuario de la imagen y ajustar la propiedad del directorio `user_data` únicamente según ese UID. Mantener el código de estrategias legible.

## Estado

Freqtrade persiste operaciones en `user_data/trades.paper.sqlite`. El control agregado conserva su estado en `user_data/risk.paper.sqlite`. El perfil generado contiene autenticación del panel y queda en `user_data/config.runtime.json`. Estos archivos están ignorados por Git.

Los logs e informes son de simulación. El descargador y el replay nunca mantienen conexiones autenticadas ni exponen funciones de compra/venta real.

## Pausas y recuperación

La pausa diaria se mantiene durante ese día UTC; la pausa por caída requiere revisión y no se borra al recuperar temporalmente el patrimonio. Un fallo de valoración impide nuevas entradas. Las salidas y stops existentes siguen procesándose mientras el bot está encendido.

Para realizar una copia coherente, detener el proceso de simulación y copiar todo `user_data` junto con versión de código y configuración. Restaurar ambos archivos de estado del mismo experimento; no mezclar una base de operaciones con un estado de riesgo de otra ejecución.

Cambiar el hash de configuración del riesgo bloquea la continuación del experimento anterior. Archivar su directorio completo y crear un nuevo experimento tras revisar el cambio; no borrar el estado para ocultar una caída. Los resultados de una nueva configuración no deben concatenarse como si fueran una sola estrategia congelada.

## Revisión semanal propuesta

Comprobar decisiones admitidas/rechazadas, posición y costes, datos vencidos, periodos sin servicio, patrimonio marcado y pausas. Evaluar diferencias entre fills modelados por Freqtrade y costes del replay. Esta es una práctica de operación, no una automatización creada por el repositorio.

## Límites de disponibilidad

Un equipo apagado no mantiene el bot ejecutándose. Los workflows de CI realizan pruebas finitas; no alojan el proceso continuo. Usar un equipo disponible durante la observación. La continuidad y las credenciales del panel se verifican antes de considerar despliegues adicionales.
