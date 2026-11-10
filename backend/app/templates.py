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
        "en": "Thanks. I can pass what you've told me to the leasing team as a tour request.",
        "es": "Gracias, lo anoté. Puedo pasar sus datos al equipo de arrendamiento como solicitud de visita.",
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
        "en": "A team member should handle this. I've written a short note so you won't have to repeat yourself. "
              "Send it to the office when you're ready.",
        "es": "Un miembro del equipo debe atender esto. Escribí una nota corta para que no tenga que repetirlo. "
              "Envíela a la oficina cuando quiera.",
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
        "en": "Your note {ref} is already saved for the office with what you told me. In this prototype nobody is "
              "notified, so please also contact the office if it's urgent. Want to send another note?",
        "es": "Su nota {ref} ya está guardada para la oficina con lo que me dijo. En este prototipo no se avisa a "
              "nadie; si es urgente, comuníquese también con la oficina. ¿Quiere enviar otra nota?",
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
              "just says how you'd like to be reached; the office will confirm your details with you.",
        "es": " Por privacidad, este prototipo no guarda teléfonos ni correos escritos en el chat, así que la nota "
              "solo indica cómo prefiere que le contacten; la oficina confirmará sus datos con usted.",
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
              "haven't saved it. When the office contacts you, you can confirm your details with them.",
        "es": "Gracias. Por privacidad, este prototipo no guarda teléfonos ni correos escritos en el chat, así que no "
              "lo guardé. Cuando la oficina le contacte, puede confirmar sus datos con ellos.",
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
        "en": "Here's what this chat has done: {sent}.{pending} In this prototype nothing reaches a real system and "
              "nobody is notified; saved items wait for a staff member to review them.",
        "es": "Esto es lo que se ha hecho en este chat: {sent}.{pending} En este prototipo nada llega a un sistema "
              "real y no se avisa a nadie; lo guardado espera a que alguien del personal lo revise.",
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
        "en": "Updated: Where → {loc}.",
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
    "repeat_heard": {
        "en": "That's not okay after this many visits, and I'm not going to ask you to troubleshoot again.",
        "es": "Eso no está bien después de tantas visitas, y no le voy a pedir que lo revise otra vez.",
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
        "en": "I'm sorry this hasn't been helpful. A person at the office can take it from here: I've written a note "
              "with what you've told me, so you won't have to repeat anything. Send it when you're ready. In this "
              "prototype nobody is notified automatically, so if it's urgent, please also contact the office.",
        "es": "Lamento que esto no le haya ayudado. Una persona de la oficina puede seguir desde aquí: escribí una "
              "nota con lo que me dijo, para que no tenga que repetir nada. Envíela cuando quiera. En este prototipo "
              "no se avisa a nadie automáticamente; si es urgente, comuníquese también con la oficina.",
    },
    "lost_note_open": {
        "en": "The note for the office is below with everything you've told me. Press \"Send note to the office\" "
              "to save it for them. In this prototype nobody is notified automatically.",
        "es": "La nota para la oficina está abajo con todo lo que me dijo. Pulse \"Enviar nota a la oficina\" para "
              "guardarla. En este prototipo no se avisa a nadie automáticamente.",
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
        "en": "{what} {ref} is saved for {team} to review, with: {saved}. In the real service the team would follow "
              "up with you. In this prototype nobody is notified automatically and no time is set, so no one will "
              "call, email or come because of this chat yet. If it's urgent, please contact the office.",
        "es": "{what} {ref} está guardada para que {team} la revise, con: {saved}. En el servicio real el equipo le "
              "daría seguimiento. En este prototipo no se avisa a nadie automáticamente ni se fija una hora, así que "
              "nadie llamará, escribirá ni vendrá todavía por este chat. Si es urgente, llame a la oficina.",
    },
    "after_send_tour": {
        "en": "Tour request {ref} is saved for the leasing team, with: {saved}. It's a request, not a booking: no "
              "time is confirmed. In the real service the leasing team would follow up to confirm a time; {route}. "
              "In this prototype nobody is notified automatically, so no one will call or email because of this chat "
              "yet.",
        "es": "La solicitud de visita {ref} está guardada para el equipo de arrendamiento, con: {saved}. Es una "
              "solicitud, no una cita: no hay hora confirmada. En el servicio real el equipo le contactaría para "
              "confirmar una hora; {route}. En este prototipo no se avisa a nadie automáticamente, así que nadie le "
              "llamará ni escribirá todavía por este chat.",
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
        "en": "I don't collect phone numbers or emails in chat yet, and there's no contact on a profile here, so "
              "nothing you type is saved. The leasing office's real contact details aren't connected to this "
              "prototype either, so for now the request can't reach you on its own.",
        "es": "Todavía no recojo teléfonos ni correos en el chat y aquí no hay un contacto en un perfil, así que lo "
              "que escriba no se guarda. Los datos de contacto reales de la oficina tampoco están conectados a este "
              "prototipo, así que por ahora la solicitud no puede llegarle por sí sola.",
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
        "en": "Request {ref} is already sent, so I can't change it here. I've prepared a note for the office to add "
              "\"{detail}\" to {ref}. Send it when you're ready.",
        "es": "La solicitud {ref} ya se envió, así que no puedo cambiarla aquí. Preparé una nota para que la oficina "
              "agregue \"{detail}\" a {ref}. Envíela cuando quiera.",
    },
    "still_stands": {
        "en": " Your {what} {ref} was already sent and still stands until the office acts on this note.",
        "es": " Su {what} {ref} ya se envió y sigue en pie hasta que la oficina atienda esta nota.",
    },
    "declined_sent_stands": {
        "en": "Okay, I haven't sent this one. Your {what} {ref} was already sent and still stands. To cancel it too, "
              "say \"cancel {ref}\" and I'll prepare a note for the office with its ID.",
        "es": "De acuerdo, esta no la envié. Su {what} {ref} ya se envió y sigue en pie. Para cancelarla también, "
              "diga \"cancelar {ref}\" y prepararé una nota para la oficina con su número.",
    },
    "priority_offer": {
        "en": "Staff set the priority when they review {ref}; I can't change it from here. I've prepared a note asking "
              "them to treat it as a priority. Send it when you're ready. In this prototype nobody is notified "
              "automatically.",
        "es": "El personal fija la prioridad cuando revisa {ref}; yo no puedo cambiarla. Preparé una nota pidiendo "
              "que la traten como prioridad. Envíela cuando quiera. En este prototipo no se avisa a nadie "
              "automáticamente.",
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
        "en": "The leasing team's follow-up isn't connected to this prototype, so nothing reaches you automatically "
              "yet.",
        "es": "El seguimiento del equipo de arrendamiento no está conectado a este prototipo, así que por ahora no le "
              "llega nada automáticamente.",
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
        "es": "Si mantenimiento llega cuando usted no está, ¿pueden entrar o prefieren contactarle primero?",
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
        "en": "Your tour request {ref} is already saved for the leasing team ({saved}). To add or change details, I "
              "can prepare a note for them. To see a different community, just tell me which one.",
        "es": "Su solicitud de visita {ref} ya está guardada para el equipo de arrendamiento ({saved}). Para agregar o "
              "cambiar datos, puedo preparar una nota. Para ver otra comunidad, dígame cuál.",
    },
    "tour_skip_slot": {  # C-6 / W-11: never "I'll leave X for the team" as if the person had declined it
        "en": "I'll mark {label} as not given yet for the leasing team to ask you about.",
        "es": "Marco {label} como pendiente, para que el equipo de arrendamiento se lo pregunte.",
    },
    # ---- sprint 5.1: answers while a card is open (TEAM DRAFTS; Spanish needs review) ----
    "q_who_sees": {
        "en": "In this prototype, only McKinley staff who review the office queue can see it, and nothing here is "
              "sent to your neighbors. I can't promise how the office handles it when they follow up; if you want "
              "your name kept out of it, add that to the note.",
        "es": "En este prototipo solo el personal de McKinley que revisa la cola de la oficina puede verlo, y nada de "
              "aquí se envía a sus vecinos. No puedo prometer cómo lo manejará la oficina; si quiere que no se "
              "mencione su nombre, agréguelo a la nota.",
    },
    "q_what_send": {
        "en": "Pressing Send saves this {what} in the prototype for staff to review. Nothing else happens: nobody "
              "is notified automatically, nothing is scheduled and nothing is charged.",
        "es": "Al pulsar Enviar, esta {what} se guarda en el prototipo para que el personal la revise. No pasa nada "
              "más: no se avisa a nadie, no se programa nada y no se cobra nada.",
    },
    "q_what_send_none": {
        "en": "There's nothing waiting to send right now. When a card is shown, pressing Send saves it in the "
              "prototype for staff to review; nobody is notified automatically and nothing is charged.",
        "es": "Ahora no hay nada pendiente de enviar. Cuando aparece una tarjeta, Enviar la guarda en el prototipo "
              "para que el personal la revise; no se avisa a nadie y no se cobra nada.",
    },
    "q_cost": {
        "en": "Nothing in this chat charges you anything: pressing Send only saves the request for staff to review. "
              "I can't speak to fees the office might set, so ask them if you're unsure.",
        "es": "Nada en este chat le cobra: Enviar solo guarda la solicitud para que el personal la revise. No puedo "
              "hablar de cargos que fije la oficina; pregúnteles si tiene dudas.",
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
        "en": "Staff set the priority when they review {ref}; I can't mark it urgent from here. In this prototype "
              "nobody is notified automatically.",
        "es": "El personal fija la prioridad cuando revisa {ref}; yo no puedo marcarla como urgente. En este "
              "prototipo no se avisa a nadie automáticamente.",
    },
    "q_timing": {
        "en": "I can't promise a call or a time. Once you press Send, it waits for staff to review; in this "
              "prototype nobody is notified automatically, so no one will call because of this chat yet.",
        "es": "No puedo prometer una llamada ni una hora. Cuando pulse Enviar, queda para revisión del personal; en "
              "este prototipo no se avisa a nadie, así que nadie llamará todavía por este chat.",
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
    "meta_sorry": {
        "en": "Sorry, you did tell me. I've got it now.",
        "es": "Perdón, sí me lo dijo. Ya lo tengo.",
    },
    "tap_send": {
        "en": "Your {what} is ready below. Tap Send to pass it on (or say \"send it\").",
        "es": "Su {what} está lista abajo. Pulse Enviar para mandarla (o diga \"envíelo\").",
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
        "en": "That sounds like {title} ({ref}), which is already open, so I won't start a duplicate. A request "
              "that's already sent can't be edited here, so I've prepared a follow-up note for the office that "
              "cites {ref}. Send it when you're ready. In this prototype nobody is notified automatically.",
        "es": "Parece ser {title} ({ref}), que ya está abierta, así que no abro otra. Una solicitud enviada no se "
              "puede editar aquí, así que preparé una nota de seguimiento para la oficina que menciona {ref}. "
              "Envíela cuando quiera. En este prototipo no se avisa a nadie automáticamente.",
    },
    "questions_note": {
        "en": "I've put your questions ({value}) in a note for the leasing team. Send it when you're ready. In this "
              "prototype nobody is notified automatically.",
        "es": "Puse sus preguntas ({value}) en una nota para el equipo de arrendamiento. Envíela cuando quiera. En "
              "este prototipo no se avisa a nadie automáticamente.",
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
        "en": "Which city or McKinley community would you like to see?",
        "es": "¿Qué ciudad o comunidad de McKinley quiere ver?",
    },
    "tour_recheck": {
        "en": "Check it over before you send it.",
        "es": "Revísela antes de enviarla.",
    },
    "field_updated": {
        "en": "Updated: {label} → {value}.",
        "es": "Actualizado: {label} → {value}.",
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
    "next_leasing_note": {
        "en": "The leasing team can answer that: I can send them your question as a note.",
        "es": "El equipo de arrendamiento puede responder: puedo enviarles su pregunta en una nota.",
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
    "maintenance_request": {
        "en": "Request {id} is saved for staff review. A team member reviews it before anything is scheduled. In "
              "this prototype nobody is notified automatically. You can ask me for its status anytime.",
        "es": "La solicitud {id} quedó guardada para revisión del personal. Un miembro del equipo la revisa antes de "
              "programar algo. En este prototipo no se avisa a nadie automáticamente. Puede preguntarme por su estado "
              "cuando quiera.",
    },
    "tour_request": {
        "en": "Tour request {id} is saved for the leasing team. It isn't a booking yet: the team picks a time from "
              "your preferences. In this prototype nobody is notified automatically.",
        "es": "La solicitud de visita {id} quedó guardada para el equipo de arrendamiento. Todavía no es una cita: el "
              "equipo elige una hora según sus preferencias. En este prototipo no se avisa a nadie automáticamente.",
    },
    "staff_handoff": {
        "en": "Note {id} is saved for the office with the details, so you won't have to repeat yourself. In this "
              "prototype nobody is notified automatically.",
        "es": "La nota {id} quedó guardada para la oficina con los detalles, para que no tenga que repetirlos. En "
              "este prototipo no se avisa a nadie automáticamente.",
    },
}

NO_CONTACT_SUFFIX: dict[Lang, str] = {
    "en": " This prototype doesn't collect a way to reach you, and the office's real contact details aren't connected "
          "here yet.",
    "es": " Este prototipo no recoge sus datos de contacto, y los datos reales de la oficina todavía no están "
          "conectados aquí.",
}

CONFIRM_LABEL: dict[str, dict[Lang, str]] = {
    "maintenance_request": {"en": "Send repair request", "es": "Enviar solicitud"},
    "tour_request": {"en": "Send tour request", "es": "Enviar solicitud de visita"},
    "staff_handoff": {"en": "Send note to the office", "es": "Enviar nota a la oficina"},
}

CHIPS: dict[str, dict[Lang, list[str]]] = {
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
