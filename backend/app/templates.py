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
        "en": "Thanks! Repairs and request status need a resident sign-in, which this public demo doesn't have. I "
              "can still answer general questions, or tap \"Talk to a person\" to leave a note for the office.",
        "es": "¡Gracias! Las reparaciones y el estado de solicitudes requieren iniciar sesión como residente, algo "
              "que esta demostración pública no tiene. Igual puedo responder preguntas generales, o toque \"Hablar "
              "con una persona\" para dejar una nota a la oficina.",
    },
    "unclear": {
        "en": "I want to make sure I get this right. Could you tell me a little more about what you need?",
        "es": "Quiero entenderle bien. ¿Me puede contar un poco más sobre lo que necesita?",
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
        "en": "Got it, let's get a repair request started. If maintenance comes while you're out, may they enter, or "
              "should they contact you first?",
        "es": "Entendido, empecemos una solicitud de reparación. Si mantenimiento llega cuando usted no está, "
              "¿pueden entrar o prefiere que le contacten primero?",
    },
    "maint_ready": {
        "en": "Thanks! Your repair request is ready below. Take a look, then send it when it looks right.",
        "es": "¡Gracias! Su solicitud de reparación está lista abajo. Revísela y envíela cuando esté bien.",
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
        "en": "Repair requests need a resident sign-in, which this public demo doesn't have. To leave a note for the "
              "office instead, tap \"Talk to a person\". For anything dangerous, call 911 now.",
        "es": "Las solicitudes de reparación requieren iniciar sesión como residente, algo que esta demostración "
              "pública no tiene. Para dejar una nota a la oficina, toque \"Hablar con una persona\". Si hay peligro, "
              "llame al 911 ahora.",
    },
    "maint_change": {
        "en": "Your {ref} is already saved, so I can't change it here. I've prepared a note for the office about the "
              "change. Send it when you're ready.",
        "es": "Su {ref} ya está guardada, así que no puedo cambiarla aquí. Preparé una nota para la oficina sobre el "
              "cambio. Envíela cuando quiera.",
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
        "en": "I don't have McKinley's office or emergency maintenance numbers in this prototype, so I can't give "
              "you one. If anyone is in danger, call 911. Your community's office or McKinley's website will have "
              "the numbers. I can also start a note for the office.",
        "es": "En este prototipo no tengo los teléfonos de las oficinas ni de mantenimiento de emergencia, así que "
              "no puedo darle uno. Si alguien corre peligro, llame al 911. La oficina de su comunidad o el sitio web "
              "de McKinley los tienen. También puedo empezar una nota para la oficina.",
    },
    "booking_q": {
        "en": "Nothing is booked yet: I can't book or confirm a specific time here. {pref}{ref}",
        "es": "Todavía no hay nada reservado: aquí no puedo reservar ni confirmar una hora. {pref}{ref}",
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
        "en": "No problem, I've changed it to {area}. Take a look before you send it.",
        "es": "Sin problema, lo cambié a {area}. Revísela antes de enviarla.",
    },
    "leasing_capture": {
        "en": "I can also start a tour request for you.",
        "es": "También puedo empezar una solicitud de visita.",
    },
    # ---- emergency (I-17/I-18 conservative placeholder) ----
    # Generic safety steps when the hazard kind is unknown ("other"). No claim about a saved note: the planner adds
    # QUEUE_NOTE only when a note really was written.
    "emergency_steps": {
        "en": "Your safety comes first. Leave the area now and call 911. If you smell gas, don't use switches or "
              "flames and call from outside. Then call your community's emergency maintenance line.",
        "es": "Su seguridad es lo primero. Salga del área ahora y llame al 911. Si huele a gas, no use "
              "interruptores ni llamas y llame desde afuera. Después llame a la línea de emergencias de "
              "mantenimiento.",
    },
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
    # Public demo, not signed in: a status question lists only what THIS conversation sent (server-issued session).
    "guest_session_status": {
        "en": "This conversation saved: {items}. It's kept in this demo and hasn't been sent to McKinley staff. "
              "Without a sign-in, I can't see requests from other visits.",
        "es": "Esta conversación guardó: {items}. Queda en esta demostración y no se envió al personal de McKinley. "
              "Sin iniciar sesión, no puedo ver solicitudes de otras visitas.",
    },
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
        "en": "I'd be happy to help you plan a visit! Which McKinley community, or which city, are you interested in?",
        "es": "¡Con gusto le ayudo a planear una visita! ¿Qué comunidad de McKinley, o qué ciudad, le interesa?",
    },
    "tour_start": {
        "en": "I'd be happy to help you plan a visit!",
        "es": "¡Con gusto le ayudo a planear una visita!",
    },
    "tour_ask_days": {
        "en": "Which days would work for a visit?",
        "es": "¿Qué días le vendrían bien para la visita?",
    },
    "tour_ask_time": {
        "en": "What time of day works best: morning, afternoon or evening?",
        "es": "¿Le conviene más en la mañana, la tarde o la noche?",
    },
    "tour_ready": {
        "en": "Perfect, your tour request is ready below. Take a look, then send it when it looks right.",
        "es": "Perfecto, su solicitud de visita está lista abajo. Revísela y envíela cuando esté bien.",
    },
    "tour_updated": {
        "en": "No problem, I've updated your tour request. Take a look before you send it.",
        "es": "Sin problema, actualicé su solicitud de visita. Revísela antes de enviarla.",
    },
    # ---- F4 FAQ (I-14 answer rules) ----
    "faq_pending": {
        "en": "I don't have approved details about {topics} to share yet, and I'd rather not guess. The leasing "
              "team can give you accurate information.",
        "es": "Todavía no tengo información aprobada sobre {topics} y prefiero no adivinar. El equipo de "
              "arrendamiento puede darle información exacta.",
    },
    "faq_live_and_pending": {  # Sprint 9, NEEDS McKINLEY REVIEW
        "en": "I can't see live {live} or approved details on {pending} here, so I won't guess. The leasing team can "
              "give you accurate, current information.",
        "es": "Aquí no veo {live} en tiempo real ni información aprobada sobre {pending}, así que no voy a adivinar. "
              "El equipo de arrendamiento puede darle información exacta y actual.",
    },
    "faq_live_unavailable": {
        "en": "I can't see live prices or availability, so I won't quote numbers that might be wrong. The leasing team "
              "has current {topics}.",
        "es": "No veo precios ni disponibilidad en tiempo real, así que no daré números que podrían estar mal. El "
              "equipo de arrendamiento tiene la información actual.",
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
    "english_switch": {
        "en": "Sure, I'll continue in English. What can I help you with?",
        "es": "Sure, I'll continue in English. What can I help you with?",
    },
    "spanish_switch_resident": {
        "en": "Of course! I can continue in Spanish.",
        "es": "¡Claro! Con gusto le ayudo en español. ¿En qué le puedo ayudar?",
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
        "en": "Of course. I've started a note for the office with what you've told me, so you won't have to repeat "
              "yourself. Send it when it looks right.",
        "es": "Por supuesto. Empecé una nota para la oficina con lo que me dijo, para que no tenga que repetirlo. "
              "Envíela cuando esté bien.",
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
        "en": "I understand why that's frustrating, especially when you've already reported it. I've drafted a note "
              "for a team member with the details below, so you won't have to start over.",
        "es": "Entiendo que sea frustrante, sobre todo si ya lo reportó. Preparé abajo una nota con los detalles "
              "para un miembro del equipo, para que no tenga que empezar de nuevo.",
    },
    "frustrated_repair": {
        "en": "I understand why that's frustrating, especially when you've already reported it. I've marked this "
              "request high priority, so that's on it when you send it.",
        "es": "Entiendo que sea frustrante, sobre todo si ya lo reportó. Marqué esta solicitud como prioridad alta, "
              "así queda indicado cuando la envíe.",
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
    "communities": {
        "en": "In this demo the communities are Heron Lake Apartments, Birchwood Commons, Sandpiper Pointe and "
              "Fernhill Apartments. I don't have approved details on prices or what's open, but I can send a tour "
              "request to the leasing team for any of them.",
        "es": "En esta demostración las comunidades son Heron Lake Apartments, Birchwood Commons, Sandpiper Pointe y "
              "Fernhill Apartments. No tengo información aprobada sobre precios ni disponibilidad, pero puedo enviar "
              "una solicitud de visita al equipo de arrendamiento.",
    },
    "safety_info_ack": {
        "en": "Those are the steps to follow if it happens. Is anything like that happening right now? If it is, "
              "follow them now and call 911.",
        "es": "Esos son los pasos a seguir si pasa. ¿Está pasando algo así ahora mismo? Si es así, sígalos ya y llame "
              "al 911.",
    },
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
        "en": "Your note {ref} is already saved with what you told me. If it's urgent, please contact the office "
              "directly too. Want to add another note?",
        "es": "Su nota {ref} ya está guardada con lo que me dijo. Si es urgente, comuníquese también directamente "
              "con la oficina. ¿Quiere agregar otra nota?",
    },
    "premise_check": {
        "en": "I can't see anything like that on your account, and I can't confirm, waive or change fees, rent, "
              "lease terms or appointments from here. I've written a note so a person can check what was agreed. "
              "Send it to the office when you're ready.",
        "es": "No veo nada así en su cuenta, y desde aquí no puedo confirmar, eximir ni cambiar cargos, renta, "
              "condiciones del contrato ni citas. Escribí una nota para que una persona revise lo acordado. Envíela "
              "a la oficina cuando quiera.",
    },
    "contact_not_kept": {
        "en": " For privacy, this prototype doesn't keep phone numbers or emails typed into the chat, so the note "
              "just says how you'd like to be reached.",
        "es": " Por privacidad, este prototipo no guarda teléfonos ni correos escritos en el chat, así que la nota "
              "solo indica cómo prefiere que le contacten.",
    },
    "multi_issue": {
        "en": "You mentioned {n} separate problems, so each gets its own request. Let's start with: {first}.",
        "es": "Mencionó {n} problemas distintos, así que cada uno tendrá su propia solicitud. Empecemos con: {first}.",
    },
    "multi_next": {
        "en": " You also mentioned: {next}. Say yes and I'll start a request for that too.",
        "es": " También mencionó: {next}. Diga sí y empiezo una solicitud para eso también.",
    },
    "legal_note": {
        "en": "I hear how frustrated you are. I can't advise on withholding rent or legal steps, and I can't decide "
              "anything about your lease, so a manager should respond to this directly. I've written a note with what "
              "you said. Send it to the office when you're ready.",
        "es": "Entiendo su frustración. No puedo aconsejar sobre retener la renta ni sobre pasos legales, ni decidir "
              "nada sobre su contrato, así que un gerente debe responderle directamente. Escribí una nota con lo que "
              "dijo. Envíela a la oficina cuando quiera.",
    },
    "other_person": {
        "en": "This chat is signed in to another resident's account, so I can't share their requests or details. If "
              "you live there too, the office can add you to the lease. I can still help with general questions.",
        "es": "Este chat está conectado a la cuenta de otro residente, así que no puedo compartir sus solicitudes ni "
              "datos. Si usted también vive ahí, la oficina puede agregarle al contrato. Puedo ayudar con preguntas "
              "generales.",
    },
    "injection_note": {
        "en": "I can't follow instructions written inside a message, and I can't confirm schedules, waive fees or "
              "change anything on an account. If there's something you need, tell me in your own words and I'll help.",
        "es": "No puedo seguir instrucciones escritas dentro de un mensaje, ni confirmar horarios, eximir cargos o "
              "cambiar nada en una cuenta. Si necesita algo, dígamelo con sus palabras y le ayudo.",
    },
    "contact_only": {
        "en": "Thanks. For privacy, this prototype doesn't keep phone numbers or emails typed into the chat, so I "
              "haven't saved it.",
        "es": "Gracias. Por privacidad, este prototipo no guarda teléfonos ni correos escritos en el chat, así que "
              "no lo guardé.",
    },
    "injection_dropped": {
        "en": "I left out the part of your message that looked like instructions to me. ",
        "es": "Omití la parte de su mensaje que parecía darme instrucciones. ",
    },
    "lockout": {
        "en": "Being locked out is stressful, especially at night. I can't unlock doors or send anyone from this chat, "
              "and nobody is notified by it. Please call your community's after-hours or emergency maintenance line "
              "now; lockouts are handled there. If you feel unsafe where you are, call 911.",
        "es": "Quedarse afuera es estresante, sobre todo de noche. Desde este chat no puedo abrir puertas ni enviar a "
              "nadie, y no se avisa a nadie. Llame ahora a la línea de mantenimiento fuera de horario o de emergencias "
              "de su comunidad; ahí atienden los cierres. Si no se siente seguro donde está, llame al 911.",
    },
    "sent_summary": {
        "en": "So far this chat has saved: {sent}.{pending} Saved items stay in this demo; nothing has been sent to "
              "McKinley staff.",
        "es": "Hasta ahora este chat guardó: {sent}.{pending} Lo guardado queda en esta demostración; no se envió "
              "nada al personal de McKinley.",
    },
    "after_send": {
        "en": "{what} ({ref}) is saved in this demo, but it hasn't been sent to {team}, so nothing is scheduled. If "
              "it's urgent, please contact the office directly.",
        "es": "{what} ({ref}) está guardada en esta demostración, pero no se envió al personal de McKinley, así que "
              "no hay nada programado. Si es urgente, comuníquese directamente con la oficina.",
    },
    "issue_updated": {
        "en": "No problem, I've changed the problem to \"{issue}\".",
        "es": "Listo, cambié el problema a \"{issue}\".",
    },
    "location_updated": {
        "en": "Got it, I've updated the room to {loc}.",
        "es": "Actualizado: Dónde → {loc}.",
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
    "repeat_heard": {  # NEEDS McKINLEY REVIEW (Sprint 8 C: 3 or more earlier requests; was "this many visits")
        "en": "I'm sorry you're dealing with this again. After this many times, I won't ask you to troubleshoot it.",
        "es": "Lamento que vuelva a pasarle. Después de tantas veces, no le voy a pedir que lo revise otra vez.",
    },
    # ---- Sprint 8 C last round (all NEEDS McKINLEY REVIEW; Spanish is a draft translation) ----
    "followup_extra_asks": {  # NEEDS McKINLEY REVIEW: a refund / credit / callback ask said with a follow-up
        "en": " You also asked for something only the office can decide. I can't promise it, but it's written on "
              "the note so they see it.",
        "es": " También pidió algo que solo la oficina puede decidir. No puedo prometerlo, pero quedó escrito en la "
              "nota para que lo vean.",
    },
    "followup_other_problem": {  # NEEDS McKINLEY REVIEW: a second, different problem in the same message
        "en": " The other problem you mentioned, \"{issue}\", gets its own repair request: it opens right after you "
              "send or skip this note.",
        "es": " El otro problema que mencionó, \"{issue}\", tendrá su propia solicitud de reparación: se abre en "
              "cuanto envíe u omita esta nota.",
    },
    "q_is_normal": {  # NEEDS McKINLEY REVIEW: "is it normal for the water heater to pop?" (a question, no form)
        "en": "I can't tell from here whether that's normal for your {thing}; a maintenance technician would need to "
              "check it. If it's happening in your home and you'd like it looked at, say \"report it\" and I'll start "
              "a repair request with you.",
        "es": "Desde aquí no puedo saber si eso es normal en su {thing}; un técnico de mantenimiento tendría que "
              "revisarlo. Si está pasando en su casa y quiere que lo revisen, diga \"reportarlo\" y empiezo una "
              "solicitud de reparación con usted.",
    },
    "payment_plan": {  # NEEDS McKINLEY REVIEW: no plan is set up or approved here
        "en": "I can't set up or approve a payment plan here; the office decides that. I've prepared a note asking "
              "them about one. Send it when you're ready.",
        "es": "Aquí no puedo crear ni aprobar un plan de pagos; eso lo decide la oficina. Preparé una nota para "
              "preguntarles. Envíela cuando quiera.",
    },
    "resume_after_alert": {  # NEEDS McKINLEY REVIEW: after the safety alert, the earlier card comes back (never
        # assumes the danger is over: the safety guidance shown earlier still applies)
        "en": "Your earlier {what} is still here and hasn't been sent. {ask}",
        "es": "Su {what} anterior sigue aquí y no se ha enviado. {ask}",
    },
    "resume_card_note": {  # NEEDS McKINLEY REVIEW: the person answered the resumed card's question
        "en": "Your earlier {what} is back, still unsent.",
        "es": "Su {what} anterior está de vuelta, todavía sin enviar.",
    },
    "praise_ack": {  # NEEDS McKINLEY REVIEW (Sprint 8 C): a compliment or small talk; no workflow starts
        "en": "Glad to hear it! If there's anything you need, like a repair or a question about your community, just "
              "tell me.",
        "es": "¡Qué bueno! Si necesita algo, como una reparación o una pregunta sobre su comunidad, solo dígame.",
    },
    "repeat_heard_one": {  # NEEDS McKINLEY REVIEW (Sprint 8 C: exactly 1 earlier request)
        "en": "You've reported this before, so I'm not going to ask you to troubleshoot again.",
        "es": "Usted ya reportó esto antes, así que no le voy a pedir que lo revise otra vez.",
    },
    "repeat_heard_two": {  # NEEDS McKINLEY REVIEW (Sprint 8 C: exactly 2 earlier requests)
        "en": "You've already reported this twice, so I'm not going to ask you to troubleshoot again.",
        "es": "Usted ya reportó esto dos veces, así que no le voy a pedir que lo revise otra vez.",
    },
    # ---- sprint 5 (TEAM DRAFTS): recovery, follow-ups, honest limits ----
    "lost_draft": {
        "en": "I'm sorry this has been confusing. {step} If you'd rather talk to a person, tap \"Talk to a person\" "
              "and I'll put everything you've told me into a note for the office, so you won't have to answer "
              "anything again.",
        "es": "Lamento la confusión. {step} Si prefiere hablar con una persona, toque \"Hablar con una persona\" y "
              "pondré todo lo que me dijo en una nota para la oficina, para que no tenga que responder nada otra vez.",
    },
    "lost_note": {
        "en": "I'm sorry this hasn't been helpful. I've written a note with what you've told me, so you won't have "
              "to repeat anything. Send it when you're ready, and if it's urgent, please contact the office directly "
              "too.",
        "es": "Lamento que esto no le haya ayudado. Escribí una nota con lo que me dijo, para que no tenga que "
              "repetir nada. Envíela cuando quiera y, si es urgente, comuníquese también directamente con la oficina.",
    },
    "lost_note_open": {
        "en": "The note for the office is below with everything you've told me. Press \"Send note to the office\" "
              "when it looks right.",
        "es": "La nota para la oficina está abajo con todo lo que me dijo. Pulse \"Enviar nota a la oficina\" cuando "
              "esté bien.",
    },
    "next_step_missing": {
        "en": "Your {what} isn't sent yet. The one thing I still need is: {label}.",
        "es": "Su {what} todavía no está enviada. Solo me falta: {label}.",
    },
    "next_step_ready": {
        "en": "Your {what} is ready below. Check it, then press Send.",
        "es": "Su {what} está lista abajo. Revísela y pulse Enviar.",
    },
    "pending_ready": {
        "en": " Your {what} is ready but not sent yet; it's waiting for you to press Send.",
        "es": " Su {what} está lista pero todavía no está enviada; espera a que pulse Enviar.",
    },
    "pending_missing": {
        "en": " Your {what} is not sent yet: it isn't finished. Still needed: {missing}.",
        "es": " Su {what} todavía no está enviada: no está completa. Falta: {missing}.",
    },
    "after_send_saved": {
        "en": "{what} ({ref}) is saved in this demo, but it hasn't been sent to {team}, so nothing is scheduled. In "
              "the real service, {team} would review it and follow up with you. If it's urgent, please contact the "
              "office directly.",
        "es": "{what} ({ref}) está guardada en esta demostración, pero no se envió al personal de McKinley, así que "
              "no hay nada programado. En el servicio real, {team} la revisaría y le daría seguimiento. Si es "
              "urgente, comuníquese directamente con la oficina.",
    },
    "after_send_tour": {
        "en": "Your tour request ({ref}) is saved in this demo, but it hasn't been sent to the leasing team, so no "
              "time is confirmed. In the real service, they'd reach out to set up a time with you.",
        "es": "Su solicitud de visita ({ref}) está guardada en esta demostración, pero no se envió al equipo de "
              "arrendamiento, así que no hay hora confirmada. En el servicio real, le contactarían para fijar una "
              "hora.",
    },
    "route_profile": {
        "en": "they would use the contact on your profile",
        "es": "usaría el contacto de su perfil",
    },
    "route_none": {
        "en": "this prototype doesn't collect a phone number or email in chat, and the office's real contact details "
              "aren't connected here",
        "es": "este prototipo no recoge teléfono ni correo en el chat, y los datos reales de la oficina no están "
              "conectados aquí",
    },
    "contact_route_profile": {
        "en": "In this prototype the leasing team follows up through the contact on your profile. I don't collect "
              "phone numbers or emails in chat yet, so nothing you type here is saved.",
        "es": "En este prototipo el equipo de arrendamiento le contacta por el contacto de su perfil. Todavía no "
              "recojo teléfonos ni correos en el chat, así que lo que escriba aquí no se guarda.",
    },
    "contact_route_none": {
        "en": "I don't collect phone numbers or emails in chat, so nothing you type is saved. This demo isn't "
              "connected to the leasing office, so the request can't reach you on its own yet.",
        "es": "No recojo teléfonos ni correos en el chat, así que lo que escriba no se guarda. Esta demostración no "
              "está conectada con la oficina de arrendamiento, así que la solicitud todavía no puede llegarle por sí "
              "sola.",
    },
    "lease_break": {
        "en": "Moving out early is handled by the leasing office directly: the options and any costs depend on your "
              "lease, and I can't quote or decide them here. I've written a note with your question for them. Send "
              "it when you're ready.",
        "es": "Mudarse antes de tiempo lo atiende directamente la oficina de arrendamiento: las opciones y cualquier "
              "costo dependen de su contrato, y yo no puedo darlos ni decidirlos aquí. Escribí una nota con su "
              "pregunta. Envíela cuando quiera.",
    },
    "maint_ask_location_door": {
        "en": "Sorry you're dealing with that. Which door is it: your front (entry) door, or a door inside the "
              "apartment? A lock that doesn't secure your home is marked high priority.",
        "es": "Lamento la molestia. ¿Qué puerta es: la puerta principal (de entrada) o una puerta dentro del "
              "apartamento? Una cerradura que no asegura su casa se marca como prioridad alta.",
    },
    "existing_request": {
        "en": "That one is {ref}: {title}. Status: {status}. I can't give repair times here. If it needs attention, "
              "I can send a note to the office about {ref}.",
        "es": "Esa es {ref}: {title}. Estado: {status}. Aquí no puedo dar horarios de reparación. Si necesita "
              "atención, puedo enviar una nota a la oficina sobre {ref}.",
    },
    # ---- sprint 5 round 2 (TEAM DRAFTS) ----
    # J-1. NEEDS McKINLEY REVIEW: shown after a self-harm / personal-safety / medical alert. The crisis line itself is
    # never written here: the planner puts the approved CARE_NOTE / NOTICE text from app/emergency.py in front of it.
    "crisis_privacy": {  # NEEDS McKINLEY REVIEW (J-1)
        "en": "About privacy: the urgent note saved in this prototype's staff queue doesn't include what you wrote. "
              "It is labelled \"{label}\" and says safety guidance was shown in the chat. Staff who review that "
              "queue can see the note, and I can't remove it, but nobody is notified automatically.",
        "es": "Sobre su privacidad: la nota urgente guardada en la cola del personal de este prototipo no incluye lo "
              "que escribió. Está marcada como \"{label}\" e indica que se mostró orientación de seguridad en el "
              "chat. El personal que revisa esa cola puede ver la nota y yo no puedo borrarla, pero no se avisa a "
              "nadie automáticamente.",
    },
    "crisis_help": {  # NEEDS McKINLEY REVIEW (J-1): a fact line; the approved hazard notice follows it verbatim
        "en": "I can't call or send anyone from here, and nobody is notified automatically.",
        "es": "Desde aquí no puedo llamar ni enviar a nadie, y no se avisa a nadie automáticamente.",
    },
    "crisis_follow": {
        "en": "Your urgent note {ref} is saved without your words, and nobody is notified automatically. I'm here if "
              "you want help with anything at home.",
        "es": "Su nota urgente {ref} está guardada sin sus palabras, y no se avisa a nadie automáticamente. Aquí estoy "
              "si quiere ayuda con algo de su casa.",
    },
    "maint_add_detail": {
        "en": "Request {ref} is already saved, so I can't change it here. I've prepared a note for the office to add "
              "\"{detail}\" to {ref}. Send it when you're ready.",
        "es": "La solicitud {ref} ya está guardada, así que no puedo cambiarla aquí. Preparé una nota para que la "
              "oficina agregue \"{detail}\" a {ref}. Envíela cuando quiera.",
    },
    "still_stands": {
        "en": " Your {what} {ref} is already saved and still stands unless this note changes it.",
        "es": " Su {what} {ref} ya está guardada y sigue igual, salvo lo que cambie esta nota.",
    },
    "declined_sent_stands": {
        "en": "Okay, I haven't sent this one. Your {what} {ref} still stands. To cancel it too, say \"cancel {ref}\" "
              "and I'll prepare a note with its reference.",
        "es": "De acuerdo, esta no la envié. Su {what} {ref} sigue guardada. Para cancelarla también, diga "
              "\"cancelar {ref}\" y prepararé una nota con su número.",
    },
    "priority_offer": {
        "en": "Staff set the priority when they review {ref}, so I can't change it from here. I've prepared a note "
              "asking them to treat it as a priority. Send it when you're ready.",
        "es": "El personal fija la prioridad cuando revisa {ref}, así que no puedo cambiarla. Preparé una nota "
              "pidiendo que la traten como prioridad. Envíela cuando quiera.",
    },
    "contact_not_saved": {
        "en": "No, I can't save phone numbers or emails here, so I haven't kept it.",
        "es": "No, aquí no puedo guardar teléfonos ni correos, así que no lo guardé.",
    },
    "contact_route_account": {
        "en": "In this prototype the office follows up through the contact preference on your account.",
        "es": "En este prototipo la oficina le contacta según la preferencia de contacto de su cuenta.",
    },
    "contact_followup_none": {
        "en": "This demo isn't connected to the leasing team, so nothing reaches you automatically yet.",
        "es": "Esta demostración no está conectada con el equipo de arrendamiento, así que por ahora no le llega "
              "nada automáticamente.",
    },
    "status_none_history": {
        "en": "I don't see any open requests on your record right now. The related requests I mentioned are earlier "
              "ones that are closed.",
        "es": "No veo solicitudes abiertas en su historial ahora. Las solicitudes relacionadas que mencioné son "
              "anteriores y están cerradas.",
    },
    "status_draft_open": {
        "en": " Your {what} in this chat isn't sent yet, so it isn't on your record.",
        "es": " Su {what} de este chat todavía no se envió, así que no aparece en su historial.",
    },
    "maint_repeat_stated": {
        "en": "I'm sorry this keeps happening. I've marked it as a repeat problem for a manager to review, not just "
              "another routine repair.",
        "es": "Lamento que siga pasando. La marqué como problema repetido para que la revise un gerente, no como una "
              "reparación de rutina.",
    },
    "other_resident": {
        "en": "I can't share another resident's information or act on their account, even for a roommate, friend or "
              "family member. They can sign in or contact the office themselves. I can send a note to the office "
              "about your own question.",
        "es": "No puedo compartir información de otro residente ni actuar en su cuenta, aunque sea su compañero de "
              "casa, amigo o familiar. Esa persona puede iniciar sesión o comunicarse con la oficina. Puedo enviar una "
              "nota a la oficina sobre su propia pregunta.",
    },
    "spanish_card": {
        "en": "Of course! I can continue in Spanish.",
        "es": "¡Claro! Seguimos en español; su solicitud sigue abajo.",
    },
    "maint_ask_entry_plain": {
        "en": "If maintenance comes while you're out, may they enter, or should they contact you first?",
        "es": "Si mantenimiento llega cuando usted no está, ¿pueden entrar o prefiere que le contacten primero?",
    },
    "questions_added": {
        "en": "Your questions are now on the note: {value}. Send it when you're ready.",
        "es": "Sus preguntas ya están en la nota: {value}. Envíela cuando quiera.",
    },
    "note_updated": {
        "en": "That's now in the note for the office. Send it when you're ready.",
        "es": "Eso ya está en la nota para la oficina. Envíela cuando quiera.",
    },
    "tour_already_sent": {
        "en": "Your tour request {ref} is already saved ({saved}). To change details, I can start a note for the "
              "leasing team, or tell me another community you'd like to see.",
        "es": "Su solicitud de visita {ref} ya está guardada ({saved}). Para cambiar datos puedo empezar una nota "
              "para el equipo de arrendamiento, o dígame otra comunidad que quiera ver.",
    },
    "tour_skip_slot": {  # C-6 / W-11: never "I'll leave X for the team" as if declined; Sprint 9: says it wasn't
        # understood
        "en": "I didn't quite catch {label}, so I've left it open for now.",
        "es": "No entendí bien {label}, así que lo dejé pendiente por ahora.",
    },
    # ---- sprint 5.1: answers while a card is open (TEAM DRAFTS; Spanish needs review) ----
    "q_who_sees": {
        "en": "In this demo, nobody at McKinley sees it, and nothing here is sent to your neighbors. In the real "
              "service, only staff who review the office queue would. If you want your name kept out of it, add that "
              "to the note.",
        "es": "En esta demostración nadie de McKinley la ve, y nada de aquí se envía a sus vecinos. En el servicio "
              "real, solo el personal que revisa la cola de la oficina la vería. Si quiere que no se mencione su "
              "nombre, agréguelo a la nota.",
    },
    "q_who_sees_plain": {
        "en": "In this demo, nobody at McKinley sees it. In the real service, only staff who review the office queue "
              "would.",
        "es": "En esta demostración nadie de McKinley la ve. En el servicio real, solo el personal que revisa la "
              "cola de la oficina la vería.",
    },
    "q_no_visit": {
        "en": "No, nothing is scheduled. This demo doesn't send requests to McKinley staff, so I can't confirm a "
              "visit or a time.",
        "es": "No, no hay nada programado. Esta demostración no envía solicitudes al personal de McKinley, así que "
              "no puedo confirmar una visita ni una hora.",
    },
    "q_count": {
        "en": "In this chat you've saved {n}: {items}.",
        "es": "En este chat ha guardado {n}: {items}.",
    },
    "q_count_none": {
        "en": "Nothing has been saved in this chat yet.",
        "es": "Todavía no se ha guardado nada en este chat.",
    },
    "q_count_open": {
        "en": " The card below isn't sent.",
        "es": " La tarjeta de abajo no está enviada.",
    },
    "ref_not_found": {
        "en": "I can't find {ref} among the requests sent in this chat or open on your record, so I can't tell you "
              "its status. Here's what is open.",
        "es": "No encuentro {ref} entre las solicitudes de este chat ni en su registro, así que no puedo darle su "
              "estado. Esto es lo que está abierto.",
    },
    "meta_sorry_nochange": {
        "en": "Sorry about that.",
        "es": "Perdone.",
    },
    "q_what_send": {
        "en": "Pressing Send saves this {what} in the demo. It isn't sent to McKinley staff, so nothing is scheduled "
              "and nothing is charged.",
        "es": "Al pulsar Enviar, esta {what} se guarda en la demostración. No se envía al personal de McKinley, así "
              "que no se programa ni se cobra nada.",
    },
    "q_what_send_none": {
        "en": "There's nothing waiting to send right now. When a card is shown, Send saves it in this demo; it isn't "
              "sent to McKinley staff and nothing is charged.",
        "es": "Ahora no hay nada pendiente de enviar. Cuando aparece una tarjeta, Enviar la guarda en esta "
              "demostración; no se envía al personal de McKinley y no se cobra nada.",
    },
    "q_cost": {
        "en": "Nothing in this chat charges you anything: pressing Send only saves the request in this demo. I can't "
              "speak to fees the office might set, so ask them if you're unsure.",
        "es": "Nada en este chat le cobra: Enviar solo guarda la solicitud en esta demostración. No puedo hablar de "
              "cargos que fije la oficina; pregúnteles si tiene dudas.",
    },
    "q_priority": {
        "en": "Staff set the priority when they review it, so I can't promise it's urgent.{flag}",
        "es": "El personal fija la prioridad cuando la revisa, así que no puedo prometer que sea urgente.{flag}",
    },
    "q_priority_flag": {
        "en": " The card already asks them to look at it: {note}.",
        "es": " La tarjeta ya les pide revisarla: {note}.",
    },
    "q_priority_sent": {
        "en": "Staff set the priority when they review {ref}, so I can't mark it urgent from here.",
        "es": "El personal fija la prioridad cuando revisa {ref}, así que no puedo marcarla como urgente.",
    },
    "q_timing": {
        "en": "I can't promise a call or a time. This demo doesn't send requests to McKinley staff, so no one will "
              "call because of this chat.",
        "es": "No puedo prometer una llamada ni una hora. Esta demostración no envía solicitudes al personal de "
              "McKinley, así que nadie llamará por este chat.",
    },
    "q_phone": {
        "en": "I don't have a phone number for the office in this prototype, so I can't connect you to a call. Your "
              "community office or McKinley's website will have it. If anyone is in danger, call 911.",
        "es": "En este prototipo no tengo el teléfono de la oficina, así que no puedo comunicarle por llamada. La "
              "oficina de su comunidad o el sitio de McKinley lo tendrán. Si alguien está en peligro, llame al 911.",
    },
    "q_gate_code": {
        "en": "I don't have gate or door codes here, and I can't share access codes in chat. The office can help "
              "with that.",
        "es": "Aquí no tengo códigos de portón ni de puertas, y no puedo compartir códigos de acceso en el chat. La "
              "oficina puede ayudarle.",
    },
    "q_renewal_card": {
        "en": "I can't see your lease dates or renewal options here; the leasing team handles renewals. Your {what} "
              "is still open below. When you're done with it, tap \"Renewal question\" and I'll prepare a note for "
              "the leasing team.",
        "es": "Aquí no veo las fechas de su contrato ni las opciones de renovación; eso lo atiende el equipo de "
              "arrendamiento. Su {what} sigue abierta abajo. Cuando termine, toque \"Pregunta de renovación\" y "
              "prepararé una nota para ellos.",
    },
    "q_name": {
        "en": "No, you don't need to give your name here. This prototype doesn't collect names or contact details "
              "in chat.",
        "es": "No, no necesita darme su nombre. Este prototipo no recoge nombres ni datos de contacto en el chat.",
    },
    "q_budget": {
        "en": "Your budget is on the card: {value}. I can't quote prices or say what's available.",
        "es": "Su presupuesto está en la tarjeta: {value}. No puedo dar precios ni decir qué hay disponible.",
    },
    "q_budget_none": {
        "en": "I haven't noted a budget yet. Tell me your monthly maximum and I'll add it for the leasing team.",
        "es": "Todavía no anoté un presupuesto. Dígame su máximo mensual y lo agrego para el equipo.",
    },
    "q_parked": {
        "en": "Not yet. Your {what} is kept as a draft: after you send or skip this note, I'll bring it back so you "
              "can send it too.",
        "es": "Todavía no. Su {what} queda guardada como borrador: cuando envíe u omita esta nota, la traigo de "
              "vuelta para que también pueda enviarla.",
    },
    "q_unknown_card": {
        "en": "I don't have an answer for that here, so I won't guess.",
        "es": "No tengo una respuesta para eso aquí, así que no voy a adivinar.",
    },
    # ---- Sprint 6 (TEAM DRAFTS, NEEDS McKINLEY REVIEW; Spanish is a draft translation) ----
    "q_history": {  # NEEDS McKINLEY REVIEW: earlier repairs from the signed-in resident's own record only
        "en": "On your account I can see earlier requests about this: {items}.",
        "es": "En su cuenta veo solicitudes anteriores sobre esto: {items}.",
    },
    "q_history_all": {  # NEEDS McKINLEY REVIEW: the resident's own repair history, nothing specific named
        "en": "These are the repair requests on your account: {items}. Tell me which one you mean, or what's wrong "
              "now.",
        "es": "Estas son las solicitudes de reparación en su cuenta: {items}. Dígame a cuál se refiere, o qué falla "
              "ahora.",
    },
    "q_history_card": {  # NEEDS McKINLEY REVIEW: earlier repairs on the same thing, with a card open
        "en": "On your account I can see earlier requests about this: {items}. Your new request below stays as it "
              "is.",
        "es": "En su cuenta veo solicitudes anteriores sobre esto: {items}. Su nueva solicitud de abajo sigue igual.",
    },
    "q_history_none_all": {  # NEEDS McKINLEY REVIEW
        "en": "I don't see any earlier repair requests on your account.",
        "es": "No veo solicitudes de reparación anteriores en su cuenta.",
    },
    "q_history_none": {  # NEEDS McKINLEY REVIEW
        "en": "I don't see an earlier repair request about this on your account.",
        "es": "No veo una solicitud de reparación anterior sobre esto en su cuenta.",
    },
    "q_history_unverified": {  # NEEDS McKINLEY REVIEW
        "en": "I can only check repair history for a signed-in resident account.",
        "es": "Solo puedo revisar el historial de reparaciones de una cuenta de residente con sesión iniciada.",
    },
    "switch_keep": {  # NEEDS McKINLEY REVIEW: "forget it, what are the pool hours?" keeps the card, unsent
        "en": "Your {what} is still below and hasn't been sent. If you don't want it, say \"cancel it\".",
        "es": "Su {what} sigue abajo y no se ha enviado. Si no la quiere, diga \"cancélela\".",
    },
    "queued_note": {  # NEEDS McKINLEY REVIEW: the other problems from the same message, each its own request
        "en": "Waiting as separate requests, after this one: {items}.",
        "es": "En espera como solicitudes aparte, después de esta: {items}.",
    },
    "location_confirmed": {  # NEEDS McKINLEY REVIEW: the room given matches the card (nothing changed)
        "en": "Thanks, that's what I have.",
        "es": "Gracias, eso es lo que tengo.",
    },
    "already_saved": {  # NEEDS McKINLEY REVIEW: idempotent save (the same request was already saved)
        "en": "{what} {ref} already has these details, so I didn't save it twice.",
        "es": "{what} {ref} ya tiene estos datos, así que no la guardé dos veces.",
    },
    "meta_sorry": {
        "en": "Sorry, you did tell me. I've got it now.",
        "es": "Perdón, sí me lo dijo. Ya lo tengo.",
    },
    "tap_send": {
        "en": "Your {what} is ready below. Tap Send when it looks right (or say \"send it\").",
        "es": "Su {what} está lista abajo. Pulse Enviar cuando esté bien (o diga \"envíelo\").",
    },
    "restored_missing": {
        "en": "Here it is again, unchanged. {ask}",
        "es": "Aquí está otra vez, sin cambios. {ask}",
    },
    "declined_status": {
        "en": "You chose not to send your {what}, so nothing was sent and nobody is coming because of it. Say "
              "\"send it after all\" to bring it back.",
        "es": "Eligió no enviar su {what}, así que no se envió nada y nadie vendrá por eso. Diga \"envíelo\" para "
              "recuperarla.",
    },
    "parked_note": {
        "en": " Your {what} is also kept as a draft: after you send or skip this note, I'll bring it back so you "
              "can send it too.",
        "es": " Su {what} también queda como borrador: cuando envíe u omita esta nota, la traigo de vuelta.",
    },
    "parked_back": {
        "en": " Your unsent {what} is back below, so you can send it too.",
        "es": " Su {what} no enviada está de nuevo abajo, para que también pueda enviarla.",
    },
    "budget_noted": {
        "en": "I've noted your budget ({value}) for the leasing team. I can't quote prices or say what's available.",
        "es": "Anoté su presupuesto ({value}) para el equipo. No puedo dar precios ni decir qué hay disponible.",
    },
    "note_added": {
        "en": "Added to the card: {value}.",
        "es": "Agregado a la tarjeta: {value}.",
    },
    "contact_updated": {
        "en": "Updated: Contact preference → {value}.",
        "es": "Actualizado: preferencia de contacto → {value}.",
    },
    "followup_existing": {
        "en": "That sounds like {title} ({ref}), which is already open, so I won't start a duplicate. A saved "
              "request can't be edited here, so I've prepared a follow-up note about it. Send it when you're ready.",
        "es": "Parece ser {title} ({ref}), que ya está abierta, así que no abro otra. Una solicitud guardada no se "
              "puede editar aquí, así que preparé una nota de seguimiento. Envíela cuando quiera.",
    },
    "questions_note": {
        "en": "I've put your questions ({value}) in a note for the leasing team. Send it when you're ready.",
        "es": "Puse sus preguntas ({value}) en una nota para el equipo de arrendamiento. Envíela cuando quiera.",
    },
    "account_boundary": {
        "en": "I can't look up or share account details in this chat unless you're signed in to that account, and "
              "saying who you are here doesn't unlock anything. If you live at McKinley, sign in to your own resident "
              "account, or I can send a note to the office.",
        "es": "No puedo consultar ni compartir datos de una cuenta en este chat si no ha iniciado sesión en esa "
              "cuenta, y decir quién es aquí no desbloquea nada. Si vive en McKinley, inicie sesión en su cuenta de "
              "residente, o puedo enviar una nota a la oficina.",
    },
    "ask_plain_issue": {
        "en": "What's wrong? A short description is fine, like \"the dishwasher won't drain.\"",
        "es": "¿Qué pasa? Basta una descripción corta, por ejemplo \"el lavaplatos no desagua\".",
    },
    "ask_plain_location": {
        "en": "Which room is it in?",
        "es": "¿En qué parte del apartamento es?",
    },
    "ask_plain_area": {
        "en": "Which McKinley community, or which city, are you interested in?",
        "es": "¿Qué comunidad de McKinley, o qué ciudad, le interesa?",
    },
    "tour_recheck": {
        "en": "Take a look before you send it.",
        "es": "Revísela antes de enviarla.",
    },
    "field_updated": {
        "en": "Updated: {label} → {value}.",
        "es": "Actualizado: {label} → {value}.",
    },
    "field_changed": {  # Sprint 9, NEEDS McKINLEY REVIEW (English only; Spanish keeps field_updated)
        "en": "Got it, I've updated {name}.",
        "es": "Listo, lo actualicé.",
    },
    "field_first": {
        "en": "{label}: {value}.",
        "es": "{label}: {value}.",
    },
    "maint_entry_confirm": {
        "en": "Just to check: if you're not home, may maintenance go in, or should they contact you first?",
        "es": "Solo para confirmar: si usted no está, ¿puede entrar mantenimiento o prefieren contactarle primero?",
    },
    "floor_plans_none": {
        "en": "I don't have verified floor plans or prices here, so I won't guess.",
        "es": "Aquí no tengo planos ni precios verificados, así que no voy a adivinar.",
    },
    # ---- Sprint 6 fix round (TEAM DRAFTS, NEEDS McKINLEY REVIEW; Spanish is a draft translation) ----
    "hold_kept": {  # NEEDS McKINLEY REVIEW: "don't send it yet" keeps the card
        "en": "Okay, I won't send it. Your {what} stays below, unsent, until you tap Send.",
        "es": "De acuerdo, no la envío. Su {what} queda abajo, sin enviar, hasta que pulse Enviar.",
    },
    "split_done": {  # NEEDS McKINLEY REVIEW: one request per problem
        "en": "Okay, I've split them: this request is now just \"{first}\". Waiting as its own request, after this "
              "one: {items}.",
        "es": "Listo, las separé: esta solicitud ahora es solo \"{first}\". En espera como solicitud aparte, después "
              "de esta: {items}.",
    },
    "split_none": {  # NEEDS McKINLEY REVIEW
        "en": "I can only see one problem on this request. Tell me the other problem and I'll make it its own request.",
        "es": "Solo veo un problema en esta solicitud. Dígame el otro problema y le hago su propia solicitud.",
    },
    # ---- Sprint 7 (all NEEDS McKINLEY REVIEW) ----
    "send_missing": {  # NEEDS McKINLEY REVIEW (Sprint 7; Sprint 9 wording)
        "en": "Almost there: still missing {missing}.",
        "es": "Casi lista: falta {missing}.",
    },
    "q_unknown_office": {  # NEEDS McKINLEY REVIEW: a question with no approved answer
        "en": "I don't have an approved answer to that here, so I won't guess. The office can tell you, and I can pass "
              "your question to them.",
        "es": "No tengo una respuesta aprobada para eso aquí, así que no voy a adivinar. La oficina se lo puede "
              "decir, y puedo pasarle su pregunta.",
    },
    "unknown_city": {  # NEEDS McKINLEY REVIEW: a place with no listed McKinley community in the demo
        "en": "I don't see a McKinley community in {area} listed in this demo. The cities listed here are Ann Arbor, "
              "Ypsilanti, Detroit, Lansing, Orlando and Tampa (communities: Heron Lake Apartments, Birchwood Commons, "
              "Sandpiper Pointe and Fernhill Apartments). I've kept your day and time: which of these would you like?",
        "es": "No veo una comunidad de McKinley en {area} en esta demostración. Las ciudades aquí son Ann Arbor, "
              "Ypsilanti, Detroit, Lansing, Orlando y Tampa (comunidades: Heron Lake Apartments, Birchwood Commons, "
              "Sandpiper Pointe y Fernhill Apartments). Guardé su día y hora: ¿cuál le interesa?",
    },
    "no_tour_ack": {  # NEEDS McKINLEY REVIEW: the prospect said no tour
        "en": "No problem, no tour. Ask me anything you'd like to know, or I can pass your questions to the leasing "
              "team.",
        "es": "Sin problema, sin visita. Pregúnteme lo que quiera saber, o puedo pasar sus preguntas al equipo de "
              "arrendamiento.",
    },
    "repair_dropped_call_kept": {  # NEEDS McKINLEY REVIEW: "cancel the oven repair, I just want the call"
        "en": "Okay, I've set the repair request aside, unsent. Your note asking for a call about \"{topic}\" is ready "
              "below. Send it when it looks right.",
        "es": "Listo, dejé la solicitud de reparación a un lado, sin enviar. Su nota pidiendo una llamada sobre "
              "\"{topic}\" está lista abajo. Envíela cuando esté correcta.",
    },
    "queued_other_safety": {  # NEEDS McKINLEY REVIEW: shown AFTER the fixed safety text, never instead of it
        "en": " Your other request (\"{topic}\") is in the same note, so it isn't lost.",
        "es": " Su otra solicitud (\"{topic}\") va en la misma nota, así que no se pierde.",
    },
    "all_clear_ack": {  # NEEDS McKINLEY REVIEW: after a safety retraction; nothing else changes
        "en": "Thanks for letting me know, I'm glad it's okay. Nothing else was changed, and the urgent note stays for "
              "staff to close. Is there anything else I can help with?",
        "es": "Gracias por avisarme, me alegra que todo esté bien. No cambié nada más y la nota urgente queda para que "
              "el personal la cierre. ¿Le ayudo con algo más?",
    },
    # ---- Sprint 8 (D) quick-fix tips before a repair request. NEEDS McKINLEY REVIEW (all four keys) ----
    "quickfix_offer": {
        "en": "Before I start a repair request, here are a few quick things that often fix this:\n{items}\n\nDid that "
              "fix it? Reply yes, or say \"send a request\" and I'll start the repair request.",
        "es": "Antes de empezar una solicitud de reparación, aquí hay unas cosas rápidas que muchas veces lo "
              "resuelven:\n{items}\n\n¿Se resolvió? Responda sí, o diga \"envíen una solicitud\" y empiezo la "
              "solicitud de reparación.",
    },
    "quickfix_draft_label": {
        "en": "Draft tips for this demo, not yet approved by McKinley. If you'd rather not try them, just say "
              "\"send a request\".",
        "es": "Consejos en borrador para esta demostración, aún no aprobados por McKinley. Si prefiere no probarlos, "
              "solo diga \"envíen una solicitud\".",
    },
    "quickfix_resolved": {
        "en": "Glad that fixed it. I haven't sent anything to maintenance. If it stops working again, just tell me "
              "and I'll start a repair request.",
        "es": "Qué bueno que se resolvió. No envié nada a mantenimiento. Si vuelve a fallar, dígame y empiezo una "
              "solicitud de reparación.",
    },
    # ---- Sprint 8 (D) fix round. NEEDS McKINLEY REVIEW (every key below) ----
    "quickfix_side_reminder": {
        "en": "About the earlier problem: did the tips fix it? Reply yes, or say \"send a request\".",
        "es": "Sobre el problema de antes: ¿lo resolvieron los consejos? Responda sí, o diga \"envíen una solicitud\".",
    },
    "quickfix_kept_first": {
        "en": "I've also kept the earlier problem ({issue}). If the tips didn't fix it, I can start that request "
              "after this one.",
        "es": "También guardé el problema de antes ({issue}). Si los consejos no lo resolvieron, puedo empezar esa "
              "solicitud después de esta.",
    },
    "quickfix_unsafe_disposal_hand": {
        "en": "No. Please never put your hand or anything else into the disposal, even when it's switched off. "
              "Leave it off and let maintenance get it out.",
        "es": "No. Por favor nunca meta la mano ni nada más en el triturador, aunque esté apagado. Déjelo apagado y "
              "que mantenimiento lo saque.",
    },
    "quickfix_unsafe_panel_cover": {
        "en": "No. Please don't take the cover off the breaker panel or tape a breaker on. Only the switches behind "
              "its door are for residents; anything else is for maintenance.",
        "es": "No. Por favor no quite la tapa del panel de breakers ni fije un breaker encendido. Solo los "
              "interruptores detrás de la puerta son para residentes; lo demás lo hace mantenimiento.",
    },
    "quickfix_unsafe_chemical_drain": {
        "en": "No. Please don't use chemical drain cleaners or boiling water. They can splash back and damage the "
              "pipes; maintenance can clear it.",
        "es": "No. Por favor no use destapacaños químicos ni agua hirviendo. Pueden salpicar y dañar la tubería; "
              "mantenimiento lo puede destapar.",
    },
    "quickfix_unsafe_wires": {
        "en": "No. Please don't touch, tape or reconnect any wires, or change an outlet yourself. Electrical work is "
              "for maintenance.",
        "es": "No. Por favor no toque, encinte ni reconecte cables, ni cambie un enchufe usted mismo. El trabajo "
              "eléctrico lo hace mantenimiento.",
    },
    "quickfix_unsafe_pesticide": {
        "en": "No. Please don't set off bug foggers or use poisons yourself: foggers can catch fire and make people "
              "and pets sick. Report it and staff can advise on pest control.",
        "es": "No. Por favor no use bombas insecticidas ni venenos usted mismo: pueden incendiarse y enfermar a "
              "personas y mascotas. Repórtelo y el personal puede orientarle sobre el control de plagas.",
    },
    "legacy_checks": {
        "en": "Meanwhile, a few checks: {items}",
        "es": "Mientras tanto: {items}",
    },
    "legacy_checks_draft": {
        "en": "Meanwhile, a few draft checks for this demo (not yet approved by McKinley): {items}",
        "es": "Mientras tanto, unas revisiones en borrador para esta demostración (aún no aprobadas por McKinley): "
              "{items}",
    },
    "quickfix_ask_again": {
        "en": "Did those steps fix it? Reply yes, or no and I'll start a repair request.",
        "es": "¿Esos pasos lo resolvieron? Responda sí, o no y empiezo una solicitud de reparación.",
    },
    "danger_no_form": {  # NEEDS McKINLEY REVIEW: no repair form while someone may be in danger
        "en": "Please follow the safety steps above first. The repair can wait: when everyone is safe, tell me about "
              "it and we can start the repair request then.",
        "es": "Por favor, siga primero los pasos de seguridad de arriba. La reparación puede esperar: cuando todos "
              "estén a salvo, cuénteme y empezamos la solicitud entonces.",
    },
    "queued_dropped": {  # NEEDS McKINLEY REVIEW: "cancel the callback, keep the faucet"
        "en": "Okay, I've taken the request for a call off. Your {what} stays as it is.",
        "es": "Listo, quité la solicitud de llamada. Su {what} sigue igual.",
    },
    "exposure_note": {  # NEEDS McKINLEY REVIEW: no heat / no AC with a vulnerable person at home
        "en": "Urgent: no heating or cooling with a vulnerable person at home",
        "es": "Urgente: sin calefacción o aire con una persona vulnerable en casa",
    },
    "exposure_lead": {  # NEEDS McKINLEY REVIEW: calm, no promise; the care line is shown by the safety layer
        "en": "With someone vulnerable at home, this repair request is marked urgent for the team to review.",
        "es": "Como hay una persona vulnerable en casa, esta solicitud de reparación queda marcada como urgente para "
              "que el equipo la revise.",
    },
    # ---- Sprint 8 Workstream C: repeat-issue history (all NEEDS McKINLEY REVIEW; Spanish is a draft translation).
    # Counts and windows come from app/maintenance_history.py (the signed-in resident's own earlier requests only; the
    # request being written now is never counted). Never say anyone was notified; no callback, refund, rent concession
    # or completion date.
    "repeat_history_many": {  # NEEDS McKINLEY REVIEW
        "en": "I can see {n} related maintenance requests {window}, so I've marked this as a repeat issue for the "
              "community manager to review.",
        "es": "Veo {n} solicitudes de mantenimiento relacionadas {window}, así que la marqué como problema repetido "
              "para que la revise el gerente de la comunidad.",
    },
    "repeat_history_one": {  # NEEDS McKINLEY REVIEW
        "en": "I can see 1 related maintenance request {window}, so I've marked this as a repeat issue for the "
              "community manager to review.",
        "es": "Veo 1 solicitud de mantenimiento relacionada {window}, así que la marqué como problema repetido para "
              "que la revise el gerente de la comunidad.",
    },
    "repeat_history_lead": {  # NEEDS McKINLEY REVIEW: the apology before the history line
        "en": "I'm sorry this is happening again.",
        "es": "Lamento que vuelva a pasar.",
    },
    "repeat_history_ready": {  # NEEDS McKINLEY REVIEW: card complete on the same turn
        "en": "Check it over, then send it.",
        "es": "Revísela y envíela.",
    },
    "repeat_history_saved": {  # NEEDS McKINLEY REVIEW: after Send; the prototype record holds the history
        "en": " It's marked as a repeat issue for community manager review, with your earlier related requests "
              "included, though in this demo no one at McKinley sees it, the community manager included.",
        "es": " Quedó marcada como problema repetido para revisión del gerente de la comunidad, con sus solicitudes "
              "relacionadas anteriores, aunque en esta demostración nadie de McKinley la ve, ni el gerente.",
    },
    "multi_issue_named": {  # NEEDS McKINLEY REVIEW: two problems in one message, the second named and queued
        "en": "You mentioned {n} separate problems, so each gets its own request. Let's start with: {first}. Waiting "
              "as its own request, after this one: {items}.",
        "es": "Mencionó {n} problemas distintos, así que cada uno tendrá su propia solicitud. Empecemos con: {first}. "
              "En espera como solicitud aparte, después de esta: {items}.",
    },
    "queued_other": {  # NEEDS McKINLEY REVIEW: a second, different need in the same message (kept, not lost)
        "en": " You also asked for the office to contact you about: \"{topic}\". I've kept that: after you send or "
              "skip this request, I'll prepare that note so you can send it too.",
        "es": " También pidió que la oficina le contacte sobre: \"{topic}\". Lo guardé: después de enviar u omitir "
              "esta solicitud, preparo esa nota para que también la pueda enviar.",
    },
    "queued_other_next": {  # NEEDS McKINLEY REVIEW
        "en": " Next, your note for the office about \"{topic}\" is ready below. Send it when it looks right.",
        "es": " Ahora, su nota para la oficina sobre \"{topic}\" está lista abajo. Envíela cuando esté correcta.",
    },
    "note_tour_added": {  # NEEDS McKINLEY REVIEW: tour details while a note for the leasing team is open
        "en": "Your tour interest ({detail}) is now part of the note for the leasing team, so nothing is lost. After "
              "you send the note, the tour request card comes next, ready for you to check. Nothing is booked yet.",
        "es": "Agregué su interés en una visita ({detail}) a la nota para el equipo de arrendamiento, así no se pierde "
              "nada. Después de enviar la nota, preparo también la solicitud de visita. Todavía no hay nada reservado.",
    },
    "tour_after_note": {  # NEEDS McKINLEY REVIEW
        "en": " Your tour request is ready below with what you told me. It isn't a booking; send it when it looks "
              "right.",
        "es": " Su solicitud de visita está lista abajo con lo que me dijo. No es una reserva; envíela cuando esté "
              "correcta.",
    },
    "date_readback_alt": {  # NEEDS McKINLEY REVIEW: "3/4" can be read two ways
        "en": "I've written {value}. If you meant {detail}, just tell me.",
        "es": "Anoté {value}. Si quiso decir {detail}, dígamelo.",
    },
    "date_readback": {  # NEEDS McKINLEY REVIEW: "tmrw" written as a date the person can check
        "en": "I've written that as {value}. Tell me if that's not the day you meant.",
        "es": "Lo anoté como {value}. Dígame si no es el día que quería.",
    },
    "near_duplicate": {  # NEEDS McKINLEY REVIEW: the same repair as one already saved in this chat
        "en": "This looks like the same repair as {ref}, which is already saved, so I didn't save it again. If it's a "
              "different problem, say \"save it as a new request\" and then tap Send.",
        "es": "Parece la misma reparación que {ref}, que ya está guardada, así que no la guardé otra vez. Si es otro "
              "problema, diga \"guardar como nueva solicitud\" y luego pulse Enviar.",
    },
    "dup_ok": {  # NEEDS McKINLEY REVIEW
        "en": "Okay, I'll treat this as a separate request. Tap Send when it looks right.",
        "es": "De acuerdo, la trato como una solicitud aparte. Pulse Enviar cuando esté correcta.",
    },
    "confused_card": {  # NEEDS McKINLEY REVIEW: "I don't understand" with a card open
        "en": "Sorry, let me put it more simply. {step}",
        "es": "Perdón, se lo digo más sencillo. {step}",
    },
    "confused_none": {  # NEEDS McKINLEY REVIEW: "I'm confused" with nothing open
        "en": "No problem. I can help you report a repair, check on your requests, answer a question, or pass a note "
              "to the office. Just tell me in your own words what you need, or tap one of the options below.",
        "es": "No se preocupe. Puedo ayudarle a reportar una reparación, revisar sus solicitudes, responder una "
              "pregunta o pasar una nota a la oficina. Dígame con sus palabras qué necesita, o elija una opción abajo.",
    },
    "frustrated_again": {  # NEEDS McKINLEY REVIEW: frustration a second time: no repeated apology, the human path
        "en": "I hear you. Your note for the office is below with everything you've told me. Send it when you're "
              "ready, and if it's urgent, please contact the office directly too.",
        "es": "Le entiendo. Su nota para la oficina está abajo con todo lo que me dijo. Envíela cuando quiera y, si "
              "es urgente, comuníquese también directamente con la oficina.",
    },
    "issue_dropped": {  # NEEDS McKINLEY REVIEW: "never mind the smoke detector, only the faucet"
        "en": "Okay, I've taken {detail} off. This request is now: \"{issue}\".",
        "es": "Listo, quité {detail}. Esta solicitud ahora es: \"{issue}\".",
    },
    "change_requested": {  # NEEDS McKINLEY REVIEW: a change after Send, cited in the change note
        "en": " The note asks for this change: {detail}.",
        "es": " La nota pide este cambio: {detail}.",
    },
    "date_which": {  # NEEDS McKINLEY REVIEW: an ordinal date with both a tour day and a move-in on the card
        "en": "Is {value} for the tour or for the move-in?",
        "es": "¿{value} es para la visita o para la mudanza?",
    },
    "staff_complaint_note": {  # NEEDS McKINLEY REVIEW: a complaint about a visit or staff member
        "en": "I'm sorry that happened. A manager should hear about this, so I've written a note with what you said. "
              "Send it to the office when you're ready.",
        "es": "Lamento que haya pasado. Un gerente debe enterarse, así que escribí una nota con lo que dijo. Envíela "
              "a la oficina cuando quiera.",
    },
    # ---- Sprint 9 (TEAM DRAFTS, NEEDS McKINLEY REVIEW; Spanish is a draft translation) ----
    "after_send_contact": {
        "en": "No, nobody will call or email from this demo, because your {what} ({ref}) wasn't sent to McKinley "
              "staff. In the real service, {team} would follow up with you.",
        "es": "No, nadie le llamará ni escribirá desde esta demostración, porque su {what} ({ref}) no se envió al "
              "personal de McKinley. En el servicio real, {team} le daría seguimiento.",
    },
    "after_send_contact_tour": {
        "en": "No, nobody will call or email from this demo, because your tour request ({ref}) wasn't sent to the "
              "leasing team, and no time is booked. In the real service, they'd reach out to set up a time.",
        "es": "No, nadie le llamará ni escribirá desde esta demostración, porque su solicitud de visita ({ref}) no se "
              "envió al equipo de arrendamiento y no hay hora reservada. En el servicio real, le contactarían para "
              "fijar una hora.",
    },
    "after_send_contact_urgent": {
        "en": "No, nobody will call or come from this demo, because your {what} ({ref}) wasn't sent to McKinley "
              "staff. If it's urgent, please contact the office directly.",
        "es": "No, nadie le llamará ni vendrá desde esta demostración, porque su {what} ({ref}) no se envió al "
              "personal de McKinley. Si es urgente, comuníquese directamente con la oficina.",
    },
    "tour_ack": {
        "en": "Sounds good!",
        "es": "¡Muy bien!",
    },
    "tour_changed": {
        "en": "No problem, I've changed it to {values}.",
        "es": "Sin problema, lo cambié a {values}.",
    },
    "tour_ready_when": {
        "en": "Perfect, I've put together your tour request for {when}. Take a look below, then send it when it "
              "looks right.",
        "es": "Perfecto, preparé su solicitud de visita para {when}. Revísela abajo y envíela cuando esté bien.",
    },
    "tour_saved_when": {
        "en": " for {when}",
        "es": " para {when}",
    },
    "booking_saved_ref": {  # Sprint 9
        "en": "Your tour request {ref} is saved in this demo only, so the leasing team hasn't received it.",
        "es": "Su solicitud de visita {ref} solo está guardada en esta demostración, así que el equipo de "
              "arrendamiento no la recibió.",
    },
    "side_resume": {  # Sprint 9, NEEDS McKINLEY REVIEW: after a second side question in a row (no repeated question)
        "en": "Whenever you're ready, we can pick your {what} back up.",
        "es": "Cuando quiera, seguimos con su {what}.",
    },
    "upset_followup_lead": {  # Sprint 9, NEEDS McKINLEY REVIEW
        "en": "I understand why that's frustrating, especially after you've already reported it.",
        "es": "Entiendo que sea frustrante, sobre todo después de haberlo reportado.",
    },
    "next_leasing_note": {
        "en": "I can pass your question to the leasing team in a note.",
        "es": "Puedo pasar su pregunta al equipo de arrendamiento en una nota.",
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
    "mix_chemicals": {"en": "Please don't mix bleach with vinegar, ammonia or other cleaners: it makes a toxic gas. "
                            "Use one product at a time with a window open.",
                      "es": "Por favor no mezcle cloro con vinagre, amoníaco u otros limpiadores: produce un gas "
                            "tóxico. Use un producto a la vez con la ventana abierta."},
    "gas_diy": {"en": "Please don't work on gas lines, valves or pilot lights yourself. If you smell gas, leave and "
                      "call 911.",
                "es": "Por favor no manipule líneas, válvulas ni pilotos de gas. Si huele a gas, salga y llame al "
                      "911."},
}

# Confirmation messages returned by the action endpoint after a prototype record was actually written (I-22,
# I-16 drafts). They state the real outcome and never promise timing.
CONFIRM: dict[str, dict[Lang, str]] = {
    # Sprint 9 (NEEDS McKINLEY REVIEW): short and truthful. The card shows the reference and details, and says once
    # that it is saved in the demo only; this line says what that means for the person (nothing sent, nothing booked).
    "maintenance_request": {
        "en": "Your repair request is saved in this demo. It hasn't been sent to maintenance, so no visit is "
              "scheduled. You can ask me about it anytime.",
        "es": "Su solicitud de reparación quedó guardada en esta demostración. No se envió a mantenimiento, así que "
              "no hay una visita programada. Puede preguntarme por ella cuando quiera.",
    },
    "tour_request": {  # {when} = " for next week in the morning" (tour_saved_when) or ""
        "en": "Your tour request{when} is saved in this demo! The time isn't confirmed, and it hasn't been sent to the "
              "leasing team.",
        "es": "¡Su solicitud de visita{when} quedó guardada en esta demostración! La hora no está confirmada y no se "
              "envió al equipo de arrendamiento.",
    },
    "staff_handoff": {
        "en": "Your note is saved in this demo with what you told me. It hasn't been sent to the office, so no one "
              "will reach out from it.",
        "es": "Su nota quedó guardada en esta demostración con lo que me dijo. No se envió a la oficina, así que "
              "nadie le contactará por ella.",
    },
    # a note with no details of the person's own (never claims "with what you told me")
    "staff_handoff_plain": {
        "en": "Your note is saved in this demo. It hasn't been sent to the office, so no one will reach out from it.",
        "es": "Su nota quedó guardada en esta demostración. No se envió a la oficina, así que nadie le contactará por "
              "ella.",
    },
}

# Sprint 9: the one demo line on a card. Before Send it says what Send will (not) do; after Send, what happened.
CARD_NOTE: dict[str, dict[str, dict[Lang, str]]] = {
    "open": {
        "maintenance_request": {"en": "Sending saves a demo request. It won't notify McKinley staff or schedule a "
                                      "visit.",
                                "es": "Enviar guarda una solicitud de demostración. No avisa al personal de McKinley "
                                      "ni programa una visita."},
        "tour_request": {"en": "Sending saves a demo request. It won't notify McKinley staff, and no time is booked.",
                         "es": "Enviar guarda una solicitud de demostración. No avisa al personal de McKinley y no "
                               "reserva una hora."},
        "staff_handoff": {"en": "Sending saves a demo note. It won't notify McKinley staff.",
                          "es": "Enviar guarda una nota de demostración. No avisa al personal de McKinley."},
    },
    "saved": {
        "maintenance_request": {"en": "Not sent to maintenance. No visit is scheduled.",
                                "es": "No se envió a mantenimiento. No hay visita programada."},
        "tour_request": {"en": "Not sent to the leasing team. No time is booked.",
                         "es": "No se envió al equipo de arrendamiento. No hay hora reservada."},
        "staff_handoff": {"en": "Not sent to the office. No one is notified.",
                          "es": "No se envió a la oficina. No se avisa a nadie."},
    },
}

CONFIRM_LABEL: dict[str, dict[Lang, str]] = {
    "maintenance_request": {"en": "Send repair request", "es": "Enviar solicitud"},
    "tour_request": {"en": "Send tour request", "es": "Enviar solicitud de visita"},
    "staff_handoff": {"en": "Send note to the office", "es": "Enviar nota a la oficina"},
}

CHIPS: dict[str, dict[Lang, list[str]]] = {
    "quickfix": {"en": ["It's fixed", "Still not working", "Send a request"],  # NEEDS McKINLEY REVIEW (Sprint 8, D)
                 "es": ["Ya funciona", "Sigue sin funcionar", "Envíen una solicitud"]},
    "locations": {"en": ["Kitchen", "Bathroom", "Bedroom", "Living room"],
                  "es": ["Cocina", "Baño", "Dormitorio", "Sala"]},
    "door_locations": {"en": ["Front door", "Bedroom", "Bathroom", "Balcony or patio"],
                       "es": ["Puerta principal", "Dormitorio", "Baño", "Balcón o patio"]},
    "lost": {"en": ["Talk to a person"], "es": ["Hablar con una persona"]},
    "ask_leasing": {"en": ["Ask the leasing team", "Request a tour"],
                    "es": ["Preguntar a arrendamiento", "Solicitar una visita"]},
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
    "safety_info": {"en": ["It's happening now", "No, just asking"], "es": ["Está pasando ahora", "No, solo pregunto"]},
    "resident_next": {"en": ["Report a repair", "Check my requests", "Talk to the office"],
                      "es": ["Reportar una reparación", "Ver mis solicitudes", "Hablar con la oficina"]},
}


def t(key: str, lang: Lang = "en", **kw: str) -> str:
    text = T[key].get(lang) or T[key]["en"]
    return text.format(**kw) if kw else text
