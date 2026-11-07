"""Deterministic customer-facing reply templates (TEAM DRAFTS, none approved by McKinley yet).

Used three ways: (1) as the backend's suggested reply passed to the response model, (2) as the reply when the
model output fails a critical validation check or the model call fails, (3) as the mock provider's reply.
Templates never promise times (I-05/I-23 not supplied), prices (D-08) or that a person was notified.
Spanish strings are DRAFT translations and need review by a fluent McKinley staff member (I-18 especially).
"""

from typing import Literal

Lang = Literal["en", "es"]

PROTOTYPE_NOTE = {
    "en": "Prototype: saved in a demo system only. No one is notified.",
    "es": "Prototipo: se guarda solo en un sistema de demostración. No se avisa a nadie.",
}

T: dict[str, dict[Lang, str]] = {
    # ---- F3 caller type (I-09 draft) ----
    "who_are_you": {
        "en": "Happy to help. Are you a current McKinley resident, or are you looking for a new home?",
        "es": "Con gusto le ayudo. ¿Ya vive en una comunidad de McKinley o está buscando un nuevo hogar?",
    },
    "guest_resident": {
        "en": "Thanks! To report a repair or check your requests, please sign in to your resident account first. "
              "I can still answer general questions while you're signed out.",
        "es": "¡Gracias! Para reportar una reparación o ver sus solicitudes, primero inicie sesión en su cuenta de "
              "residente. Mientras tanto puedo responder preguntas generales.",
    },
    "unclear": {
        "en": "I want to make sure I get this right. Could you tell me a little more about what you need?",
        "es": "Quiero entenderle bien. ¿Me puede contar un poco más sobre lo que necesita?",
    },
    "unclear_twice": {
        "en": "I'm sorry I'm not getting this right. A person on our team can sort it out with you. "
              "I've prepared a note for the office below; send it when you're ready.",
        "es": "Disculpe, no le estoy entendiendo bien. Una persona de nuestro equipo puede ayudarle. "
              "Preparé una nota para la oficina abajo; envíela cuando quiera.",
    },
    # ---- F6 maintenance intake (I-19 draft) ----
    "maint_ask_what": {
        "en": "Sorry it's not working. What is it that isn't working? For example, the dishwasher or the bathroom "
              "light.",
        "es": "Lamento que no funcione. ¿Qué es lo que no funciona? Por ejemplo, el lavaplatos o la luz del baño.",
    },
    "maint_ask_issue": {
        "en": "I can help you report that. What's going on? A short description is fine, like \"bathroom sink "
              "is leaking.\"",
        "es": "Puedo ayudarle a reportarlo. ¿Qué está pasando? Basta una descripción corta, por ejemplo "
              "\"el lavabo del baño gotea\".",
    },
    "maint_ask_location": {
        "en": "Sorry you're dealing with that. Which room is it in?",
        "es": "Lamento la molestia. ¿En qué parte del apartamento es?",
    },
    "maint_ask_entry": {
        "en": "Got it. If maintenance comes while you're out, may they enter, or should they contact you first?",
        "es": "Entendido. Si mantenimiento llega cuando usted no está, ¿pueden entrar o prefieren contactarle "
              "primero?",
    },
    "maint_ready": {
        "en": "Thanks. Here's your request. Check it over, then send it when it looks right.",
        "es": "Gracias. Aquí está su solicitud. Revísela y envíela cuando esté correcta.",
    },
    "maint_ready_repeat": {
        "en": "I'm sorry this keeps happening. I can see related requests on your record, so I've marked this one "
              "as a repeat issue for a manager to review instead of a routine repair. Check it over, then send it.",
        "es": "Lamento que esto siga pasando. Veo solicitudes relacionadas en su historial, así que la marqué como "
              "problema repetido para que la revise un gerente. Revísela y envíela.",
    },
    "maint_repeat_ack": {
        "en": "I'm sorry this is happening again. I can see related requests on your record, so I'll mark this as "
              "a repeat issue for a manager to review, not just another routine repair.",
        "es": "Lamento que vuelva a pasar. Veo solicitudes relacionadas en su historial, así que la marcaré como "
              "problema repetido para que la revise un gerente.",
    },
    "maint_unverified": {
        "en": "I can't match you to a resident account here, so I can't file a repair request for a unit. "
              "The office can take it from you directly. If water, gas, smoke or sparks are involved, call 911 or "
              "your community's emergency maintenance line now.",
        "es": "No puedo vincularle con una cuenta de residente aquí, así que no puedo registrar una solicitud. "
              "La oficina puede tomarla directamente. Si hay agua, gas, humo o chispas, llame al 911 o a la línea "
              "de emergencias de mantenimiento ahora.",
    },
    "maint_guest": {
        "en": "Repair requests come from residents signed in to their account. If you live at a McKinley "
              "community, sign in and I'll take the details. For anything dangerous, call 911 now.",
        "es": "Las solicitudes de reparación las hacen residentes con su cuenta. Si vive en una comunidad de "
              "McKinley, inicie sesión y tomaré los detalles. Si hay peligro, llame al 911 ahora.",
    },
    "maint_change": {
        "en": "A team member makes changes to requests that are already sent. I've prepared a note for the office "
              "that includes {ref}. Send it when you're ready.",
        "es": "Los cambios a solicitudes ya enviadas los hace un miembro del equipo. Preparé una nota para la oficina "
              "con {ref}. Envíela cuando quiera.",
    },
    "no_promise": {
        "en": "I can't promise a date, a credit or any outcome; a team member decides that. Your request is "
              "in the details so the office sees it.",
        "es": "No puedo prometer una fecha, un crédito ni un resultado; eso lo decide un miembro del equipo. Agregué"
              " su "
              "petición a los detalles para que la oficina la vea.",
    },
    "no_promise_note": {
        "en": "I can't promise a credit, a date or any outcome; a team member decides that. I've prepared a note so "
              "the office can review your request.",
        "es": "No puedo prometer un crédito, una fecha ni un resultado; eso lo decide un miembro del equipo. Preparé "
              "una nota para que la oficina revise su petición.",
    },
    "listening": {
        "en": "I'm sorry, I hear you, and you shouldn't have to repeat yourself. I already have your details below.",
        "es": "Lo siento, le escucho, y no debería tener que repetirlo. Ya tengo sus datos abajo.",
    },
    "noise": {
        "en": "That sounds exhausting, I'm sorry. Noise between neighbors is handled by the community team, so I've "
              "prepared a note for them. Send it when you're ready.",
        "es": "Eso suena agotador, lo siento. El ruido entre vecinos lo atiende el equipo de la comunidad; preparé una "
              "nota para ellos. Envíela cuando quiera.",
    },
    "balance": {
        "en": "I can't see balances or payments here. The office can go over your account with you, so I've prepared "
              "a note for them.",
        "es": "Aquí no puedo ver saldos ni pagos. La oficina puede revisar su cuenta con usted; preparé una nota.",
    },
    "unknown_ref": {
        "en": " I don't see {ref} among the requests in this conversation, so the note asks the office to check that "
              "reference.",
        "es": " No veo {ref} entre las solicitudes de esta conversación; la nota le pide a la oficina revisarla.",
    },
    "nothing_pending": {
        "en": "There's nothing waiting to be sent right now. What would you like to do?",
        "es": "No hay nada pendiente de enviar. ¿Qué le gustaría hacer?",
    },
    "reshow": {
        "en": "Before I send anything: here's the {title} you started earlier. Does it still look right?",
        "es": "Antes de enviar nada: aquí está la {title} que empezó antes. ¿Sigue siendo correcta?",
    },
    "emergency_follow": {
        "en": "Your urgent note {ref} is saved, but this assistant hasn't sent anyone. If you haven't yet, call your "
              "community's emergency maintenance line. If anyone feels unwell or is in danger, call 911.",
        "es": "Su nota urgente {ref} está guardada, pero este asistente no ha enviado a nadie. Si aún no lo hizo, "
              "llame a la línea de emergencias de mantenimiento. Si alguien se siente mal o corre peligro, "
              "llame al 911.",
    },
    "small_thanks": {
        "en": "You're welcome. Is there anything else I can help with?",
        "es": "Con gusto. ¿Le ayudo con algo más?",
    },
    "small_hi": {
        "en": "Hi! What can I help you with today?",
        "es": "¡Hola! ¿En qué le puedo ayudar hoy?",
    },
    "small_bye": {
        "en": "Thanks for reaching out. Take care!",
        "es": "Gracias por escribir. ¡Que esté bien!",
    },
    "phone_number": {
        "en": "I don't have McKinley's office or emergency maintenance numbers in this prototype, so I can't give you "
              "one. If anyone is in danger, call 911. Your community's office or McKinley's website will have the "
              "numbers. I can also send a note to the office.",
        "es": "En este prototipo no tengo los teléfonos de las oficinas, así que no puedo darle uno. La oficina de su "
              "comunidad o el sitio web de McKinley lo tienen. También puedo enviar una nota a la oficina.",
    },
    "booking_q": {
        "en": "I can't book or confirm a specific time. {pref}The leasing team picks the time and confirms it with you"
              ", so nothing is booked yet.{ref}",
        "es": "No puedo reservar ni confirmar una hora. {pref}El equipo de arrendamiento elige la hora y se la "
              "confirma, así que todavía no hay nada reservado.{ref}",
    },
    "eviction": {
        "en": "That sounds really stressful. I can't make decisions about your lease, and nothing you say here changes "
              "your account. The office can explain where things stand, and your question is in the note.",
        "es": "Eso suena muy estresante. No puedo tomar decisiones sobre su contrato y nada de lo que diga aquí cambia "
              "su cuenta. La oficina puede explicarle su situación; agregué su pregunta a la nota.",
    },
    "sms_opt_in": {
        "en": "You're subscribed to McKinley assistant texts again. Reply STOP to opt out. (Prototype: no texts are "
              "actually sent.)",
        "es": "Volvió a suscribirse a los mensajes del asistente de McKinley. Responda STOP para cancelar. "
              "(Prototipo: no se envían mensajes reales.)",
    },
    "tour_area_updated": {
        "en": "Updated to {area}. Check it over before you send it.",
        "es": "Actualizado a {area}. Revísela antes de enviarla.",
    },
    "leasing_capture": {
        "en": "Thanks, I've noted that. I can pass your details to the leasing team as a tour request.",
        "es": "Gracias, lo anoté. Puedo pasar sus datos al equipo de arrendamiento como solicitud de visita.",
    },
    # ---- emergency (I-17/I-18 conservative placeholder) ----
    "emergency": {
        "en": "Your safety comes first. Leave the area now and call 911. If you smell gas, don't use switches or "
              "flames and call from outside. Then call your community's emergency maintenance line. An urgent "
              "note is saved in the staff queue, but this prototype can't page anyone, so please make those calls.",
        "es": "Su seguridad es lo primero. Salga del área ahora y llame al 911. Si huele a gas, no use "
              "interruptores ni llamas y llame desde afuera. Después llame a la línea de emergencias de "
              "mantenimiento. Dejé una nota urgente para el personal, pero este prototipo no puede avisar a nadie, "
              "así que por favor haga esas llamadas.",
    },
    # ---- F8 status lookup ----
    "status_none": {
        "en": "I don't see any open requests on your record right now. If something isn't fixed, I can help you "
              "report it.",
        "es": "No veo solicitudes abiertas en su historial ahora. Si algo no está arreglado, puedo ayudarle a "
              "reportarlo.",
    },
    "status_some": {
        "en": "Here's what's open on your record. I can't give repair times here. If something has waited too long, "
              "I can send a note to the office.",
        "es": "Esto es lo que está abierto en su historial. Todavía no tengo horarios de reparación para "
              "compartir. Si algo lleva demasiado tiempo, puedo enviar una nota a la oficina.",
    },
    "status_some_short": {
        "en": "Here's what's open on your record. I don't have repair times to share yet.",
        "es": "Esto es lo que está abierto en su historial. Todavía no tengo horarios de reparación.",
    },
    "status_unverified": {
        "en": "I can't share request or account details until you're signed in to your resident account. "
              "The office can look it up after confirming who you are. I've prepared a note for them.",
        "es": "No puedo compartir detalles de solicitudes o cuentas hasta que inicie sesión en su cuenta de "
              "residente. La oficina puede buscarlo después de confirmar su identidad. Preparé una nota para ellos.",
    },
    # ---- F5 tour scheduling (I-15/I-16 drafts) ----
    "tour_ask_area": {
        "en": "I'd be glad to set up a tour request. Which city or McKinley community would you like to see?",
        "es": "Con gusto preparo una solicitud de visita. ¿Qué ciudad o comunidad de McKinley quiere ver?",
    },
    "tour_start": {
        "en": "I'd be glad to set up a tour request for you.",
        "es": "Con gusto preparo una solicitud de visita.",
    },
    "tour_ask_days": {
        "en": "Which days work for you to visit?",
        "es": "¿Qué días le funcionan para la visita?",
    },
    "tour_ask_time": {
        "en": "What time of day is easiest: morning, afternoon or evening?",
        "es": "¿Qué hora del día le conviene más: mañana, tarde o noche?",
    },
    "tour_ready": {
        "en": "Here's your tour request. The leasing team picks the exact time, so this isn't a booking yet. "
              "Send it when it looks right.",
        "es": "Aquí está su solicitud de visita. El equipo de arrendamiento elige la hora exacta, así que todavía no "
              "es una cita confirmada. Envíela cuando esté correcta.",
    },
    "tour_updated": {
        "en": "No problem, I've updated your tour request. Check it over before you send it.",
        "es": "Sin problema, actualicé su solicitud de visita. Revísela antes de enviarla.",
    },
    # ---- F4 FAQ (I-14 answer rules) ----
    "faq_pending": {
        "en": "I don't have approved details about {topics} to share yet, and I'd rather not guess. The leasing "
              "team can give you accurate information.",
        "es": "Todavía no tengo información aprobada sobre {topics} y prefiero no adivinar. El equipo de "
              "arrendamiento puede darle información exacta.",
    },
    "faq_live_unavailable": {
        "en": "I can't see live prices or what's available today, so I won't quote a number that might be wrong. "
              "The leasing team has current {topics}.",
        "es": "No tengo acceso a precios ni disponibilidad en tiempo real, así que no daré un número que podría "
              "estar mal. El equipo de arrendamiento tiene la información actual.",
    },
    "faq_offer_tour": {
        "en": "Would you like to request a tour?",
        "es": "¿Le gustaría solicitar una visita?",
    },
    "leasing_welcome": {
        "en": "Welcome! I can answer general questions and send a tour request to the leasing team.",
        "es": "¡Bienvenido! Puedo responder preguntas generales y enviar una solicitud de visita al equipo de "
              "arrendamiento.",
    },
    # ---- I-13 steering (draft neutral redirect; legal must approve) ----
    "steering": {
        "en": "I can't describe or compare communities by who lives there. Every community is open to everyone. "
              "I'm happy to help with what matters for your home, like the number of beds, your budget, location "
              "or move-in date.",
        "es": "No puedo describir ni comparar comunidades según quién vive en ellas. Todas están abiertas a "
              "todos. Con gusto le ayudo con lo que importa para su hogar: número de recámaras, presupuesto, "
              "ubicación o fecha de mudanza.",
    },
    "steering_family": {
        "en": "Families, including families expecting a baby, are welcome at every McKinley community. The leasing "
              "team can explain the occupancy guidelines for each floor plan.",
        "es": "Las familias, incluidas las que esperan un bebé, son bienvenidas en todas las comunidades de McKinley. "
              "El equipo de arrendamiento puede explicar las normas de ocupación de cada plano.",
    },
    "steering_safety": {
        "en": "I can't describe how safe an area is. Your local police department's public crime map is a good "
              "source, and you're welcome to tour the community and see it for yourself.",
        "es": "No puedo describir qué tan segura es una zona. El mapa público de delitos de la policía local es una "
              "buena fuente, y puede visitar la comunidad para verla usted mismo.",
    },
    "spanish_switch": {
        "en": "Of course! I can continue in Spanish.",
        "es": "¡Claro! Con gusto le ayudo en español. ¿Busca un hogar o ya vive en una comunidad de McKinley?",
    },
    "accommodation": {
        "en": "Thank you for telling me. Requests like this are handled by a trained team member, who can go "
              "through it with you. I've prepared a note for the office.",
        "es": "Gracias por decírmelo. Estas solicitudes las atiende un miembro capacitado del equipo, quien la "
              "revisará con usted. Preparé una nota para la oficina.",
    },
    # ---- F3 vendor (D-06) ----
    "vendor": {
        "en": "Thanks for reaching out. Vendor questions, including access, scheduling and invoices, go to the "
              "property management team. I can't share access codes or resident information here.",
        "es": "Gracias por comunicarse. Las preguntas de proveedores (acceso, horarios, facturas) las atiende el "
              "equipo de administración. No puedo compartir códigos de acceso ni información de residentes.",
    },
    # ---- F9 handoff (I-27) ----
    "handoff_offer": {
        "en": "Of course. A team member should handle this. I've written a short note so you won't have to repeat "
              "yourself. Send it to the office when you're ready.",
        "es": "Por supuesto. Un miembro del equipo debe atender esto. Escribí una nota corta para que no tenga que "
              "repetirlo. Envíela a la oficina cuando quiera.",
    },
    "sensitive": {
        "en": "Please don't share card numbers, Social Security numbers or birth dates in chat. I've hidden what "
              "you sent. Payments and account questions are handled by the office, and I've prepared a note for "
              "them.",
        "es": "Por favor no comparta números de tarjeta, de Seguro Social ni fechas de nacimiento por chat. Oculté "
              "lo que envió. Los pagos y preguntas de cuenta los atiende la oficina; preparé una nota para ellos.",
    },
    "renewal": {
        "en": "I understand. Renewal decisions are a big deal, and the leasing office can walk you through your "
              "options. I can't quote or change renewal terms myself. I've prepared a note for them{contact}.",
        "es": "Le entiendo. La renovación es una decisión importante y la oficina puede explicarle sus opciones. "
              "Yo no puedo dar ni cambiar condiciones de renovación. Preparé una nota para ellos{contact}.",
    },
    "frustrated": {
        "en": "I'm sorry. That's frustrating, and you shouldn't have to keep chasing this. A team member should "
              "look at it, so I've drafted a note with the details below. Send it and you won't have to start over.",
        "es": "Lo siento, es frustrante y no debería tener que insistir. Un miembro del equipo debe revisarlo, así que "
              "preparé abajo una nota con los detalles. Envíela y no tendrá que empezar de nuevo.",
    },
    "frustrated_repair": {
        "en": "I'm sorry. That's frustrating, and you shouldn't have to keep chasing this. When you send this request "
              "it will be marked high priority for a manager to review.",
        "es": "Lo siento, es frustrante y no debería tener que insistir. Cuando envíe esta solicitud quedará marcada "
              "como prioridad alta para que la revise un gerente.",
    },
    "other_language": {
        "en": "If this is an emergency, call 911. Si es una emergencia, llame al 911. I can reply in English or "
              "Spanish. For other languages, a team member can help, and I've prepared a note for the office.",
        "es": "Si es una emergencia, llame al 911. Puedo responder en inglés o español. Para otros idiomas, un "
              "miembro del equipo puede ayudarle.",
    },
    # ---- F2 SMS (I-06 draft; compliance must approve) ----
    "sms_opt_out": {
        "en": "You're unsubscribed from McKinley assistant texts. Reply START to opt back in. "
              "(Prototype: no texts are actually sent.)",
        "es": "Se canceló su suscripción a los mensajes del asistente de McKinley. Responda START para volver. "
              "(Prototipo: no se envían mensajes reales.)",
    },
    "resident_general": {
        "en": "I can help with repair requests, checking your open requests, renewal questions, or getting you to "
              "the office. What would you like to do?",
        "es": "Puedo ayudarle con solicitudes de reparación, revisar sus solicitudes abiertas, preguntas de "
              "renovación o comunicarle con la oficina. ¿Qué le gustaría hacer?",
    },
    "declined": {
        "en": "Okay, I haven't sent it. If you change your mind, say \"send it after all\". Anything else?",
        "es": "De acuerdo, no lo envié. Si cambia de opinión, diga \"envíelo\". ¿Algo más?",
    },
    # ---- sprint 2 (TEAM DRAFTS) ----
    "distress_ack": {
        "en": "That sounds like a lot to carry right now. There's no rush here. If you'd like help with anything at "
              "home, just tell me what's going on.",
        "es": "Parece que está cargando con mucho ahora. Aquí no hay prisa. Si quiere ayuda con algo de su casa, "
              "cuénteme qué pasa.",
    },
    "restored": {
        "en": "Here it is again, unchanged. Send it when it looks right.",
        "es": "Aquí está otra vez, sin cambios. Envíela cuando esté bien.",
    },
    "unclear_offer": {
        "en": "Sorry, I didn't follow that. Could you say it another way? Or I can pass what you've written to the "
              "office.",
        "es": "Disculpe, no le entendí. ¿Lo puede decir de otra forma? O puedo pasar lo que escribió a la oficina.",
    },
    "note_exists": {
        "en": "Your note {ref} is already saved for the office with what you told me. In this prototype nobody is "
              "notified, so please also contact the office if it's urgent. Want to send another note?",
        "es": "Su nota {ref} ya está guardada para la oficina con lo que me dijo. En este prototipo no se avisa a "
              "nadie; si es urgente, comuníquese también con la oficina. ¿Quiere enviar otra nota?",
    },
    "after_send": {
        "en": "{what} {ref} is saved for {team} to review. In this prototype nobody is notified and no time is set, "
              "so no one will call or come because of this chat yet. If it's urgent, please contact the office.",
        "es": "{what} {ref} está guardada para que {team} la revise. En este prototipo no se avisa a nadie ni se fija "
              "una hora, así que nadie llamará ni vendrá todavía por este chat. Si es urgente, llame a la oficina.",
    },
    "issue_updated": {
        "en": "No problem, I've changed the problem to \"{issue}\".",
        "es": "Listo, cambié el problema a \"{issue}\".",
    },
    "location_updated": {
        "en": "Updated: the location is now {loc}.",
        "es": "Actualizado: el lugar ahora es {loc}.",
    },
    "contact_noted": {
        "en": "This request now includes \"{pref}\" for the team. I can't change your account's contact settings "
              "from here; the office can.",
        "es": "Agregué \"{pref}\" a esta solicitud para el equipo. No puedo cambiar sus preferencias de contacto "
              "desde aquí; la oficina sí puede.",
    },
    "contact_note_offer": {
        "en": "I can't change your contact settings from here, but I can send \"{pref}\" to the office. The note is "
              "below.",
        "es": "No puedo cambiar sus preferencias de contacto desde aquí, pero puedo enviar \"{pref}\" a la "
              "oficina. La nota está abajo.",
    },
    "policy_unknown": {
        "en": "I don't have approved details about {topic} yet, so I won't guess. The office can answer that, and I "
              "can send them your question.",
        "es": "Todavía no tengo información aprobada sobre {topic}, así que no voy a adivinar. La oficina puede "
              "responder y puedo enviarles su pregunta.",
    },
    "price_claim": {
        "en": "I can't confirm prices or specials, or hold a rate, from here. The leasing team confirms current "
              "pricing and any special. I can include what you saw so they can check it.",
        "es": "No puedo confirmar precios ni ofertas especiales, ni reservar una tarifa desde aquí. El equipo de "
              "arrendamiento confirma los precios y ofertas vigentes. Puedo incluir lo que vio para que lo revisen.",
    },
    "repeat_heard": {
        "en": "That's not okay after this many visits, and I'm not going to ask you to troubleshoot again.",
        "es": "Eso no está bien después de tantas visitas, y no le voy a pedir que lo revise otra vez.",
    },
}

# Unsafe do-it-yourself steps: what to say instead (TEAM DRAFTS; McKinley maintenance must approve).
DIY_ADVICE: dict[str, dict[Lang, str]] = {
    "breaker": {"en": "Please don't tape or hold a breaker on. A breaker that keeps tripping is protecting the "
                      "wiring; leave it off and let maintenance check it.",
                "es": "Por favor no fije ni sostenga un breaker encendido. Si se baja seguido, está protegiendo el "
                      "cableado; déjelo apagado y que mantenimiento lo revise."},
    "disposal": {"en": "Please never put your hand in the disposal, even when it's off. Leave it for maintenance.",
                 "es": "Por favor nunca meta la mano en el triturador, aunque esté apagado. Déjelo a mantenimiento."},
    "wiring": {"en": "Please don't open or rewire outlets, switches or the panel yourself. Maintenance needs to do "
                     "electrical work.",
               "es": "Por favor no abra ni cambie enchufes, interruptores o el panel usted mismo. El trabajo eléctrico "
                     "lo hace mantenimiento."},
    "space_heater": {"en": "Please don't use a space heater in the bathroom or near water. If the bathroom is too "
                           "cold, that's a heating repair.",
                     "es": "Por favor no use un calentador portátil en el baño ni cerca del agua. Si el baño está muy "
                           "frío, es una reparación de calefacción."},
    "detector_battery": {"en": "Please keep the battery in your smoke or CO detector. If it goes off while you cook, "
                               "open a window or use the fan, and maintenance can check or move it.",
                         "es": "Por favor no le quite la batería al detector de humo o CO. Si suena al cocinar, abra "
                               "una ventana o use el extractor, y mantenimiento puede revisarlo o moverlo."},
    "gas_diy": {"en": "Please don't work on gas lines, valves or pilot lights yourself. If you smell gas, leave and "
                      "call 911.",
                "es": "Por favor no manipule líneas, válvulas ni pilotos de gas. Si huele a gas, salga y llame al "
                      "911."},
}

# Confirmation messages returned by the action endpoint after a prototype record was actually written (I-22,
# I-16 drafts). They state the real outcome and never promise timing.
CONFIRM: dict[str, dict[Lang, str]] = {
    "maintenance_request": {
        "en": "Request {id} is saved for staff review. A team member reviews it before anything is scheduled. You "
              "can ask me for its status anytime.",
        "es": "La solicitud {id} quedó guardada para revisión del personal. Un miembro del equipo la revisa antes de "
              "programar algo. Puede preguntarme por su estado cuando quiera.",
    },
    "tour_request": {
        "en": "Tour request {id} is saved for the leasing team. It isn't a booking yet: the team picks a time from "
              "your preferences.",
        "es": "La solicitud de visita {id} quedó guardada para el equipo de arrendamiento. Todavía no es una cita: el "
              "equipo elige una hora según sus preferencias.",
    },
    "staff_handoff": {
        "en": "Note {id} is saved for the office with the details, so you won't have to repeat yourself.",
        "es": "La nota {id} quedó guardada para la oficina con los detalles, para que no tenga que repetirlos.",
    },
}

NO_CONTACT_SUFFIX: dict[Lang, str] = {
    "en": " This prototype doesn't collect a way to reach you, so please also contact the office directly.",
    "es": " Este prototipo no recoge sus datos de contacto, así que por favor comuníquese también con la oficina.",
}

CONFIRM_LABEL: dict[str, dict[Lang, str]] = {
    "maintenance_request": {"en": "Send repair request", "es": "Enviar solicitud"},
    "tour_request": {"en": "Send tour request", "es": "Enviar solicitud de visita"},
    "staff_handoff": {"en": "Send note to the office", "es": "Enviar nota a la oficina"},
}

CHIPS: dict[str, dict[Lang, list[str]]] = {
    "locations": {"en": ["Kitchen", "Bathroom", "Bedroom", "Living room"],
                  "es": ["Cocina", "Baño", "Dormitorio", "Sala"]},
    "entry": {"en": ["Yes, you can enter", "Contact me first"],
              "es": ["Sí, pueden entrar", "Llamen antes"]},
    "who": {"en": ["I live at McKinley", "I'm looking for a home"],
            "es": ["Vivo en McKinley", "Busco un hogar"]},
    "tour_days": {"en": ["This weekend", "Weekdays", "Next week"], "es": ["Este fin de semana", "Entre semana"]},
    "tour_time": {"en": ["Morning", "Afternoon", "Evening"], "es": ["Mañana", "Tarde", "Noche"]},
    "prospect_next": {"en": ["Request a tour", "Talk to the leasing team"],
                      "es": ["Solicitar una visita", "Hablar con arrendamiento"]},
    "after_decline": {"en": ["Send it after all", "Report a repair", "Talk to the office"],
                      "es": ["Envíelo", "Reportar una reparación", "Hablar con la oficina"]},
    "unclear": {"en": ["Send a note to the office", "Report a repair", "Check my requests"],
                "es": ["Enviar nota a la oficina", "Reportar una reparación", "Ver mis solicitudes"]},
    "ask_office": {"en": ["Ask the office"], "es": ["Preguntar a la oficina"]},
    "resident_next": {"en": ["Report a repair", "Check my requests", "Talk to the office"],
                      "es": ["Reportar una reparación", "Ver mis solicitudes", "Hablar con la oficina"]},
}


def t(key: str, lang: Lang = "en", **kw: str) -> str:
    text = T[key].get(lang) or T[key]["en"]
    return text.format(**kw) if kw else text
