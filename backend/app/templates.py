"""Deterministic customer-facing reply templates (TEAM DRAFTS, none approved by McKinley yet).

Used three ways: (1) as the backend's suggested reply passed to the response model, (2) as the reply when the
model output fails a critical validation check or the model call fails, (3) as the mock provider's reply.
Templates never promise times (I-05/I-23 not supplied), prices (D-08) or that a person was notified.
Spanish strings are DRAFT translations and need review by a fluent McKinley staff member (I-18 especially).
"""

from typing import Literal

Lang = Literal["en", "es"]

PROTOTYPE_NOTE = {
    "en": "Prototype: saved in the McKinley demo system only. No one is notified and nothing goes to Yardi.",
    "es": "Prototipo: se guarda solo en el sistema de demostración. No se notifica a nadie ni se envía a Yardi.",
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
        "en": "Changes or cancellations to an existing request are handled by a team member, because the rules "
              "for each request stage haven't been set for the assistant. I've prepared a note for the office.",
        "es": "Los cambios o cancelaciones de una solicitud los hace un miembro del equipo. Preparé una nota para "
              "la oficina.",
    },
    # ---- emergency (I-17/I-18 conservative placeholder) ----
    "emergency": {
        "en": "Your safety comes first. Leave the area now and call 911. If you smell gas, don't use switches or "
              "flames and call from outside. Then call your community's emergency maintenance line. I've added an "
              "urgent note to the staff queue, but this prototype can't page anyone, so please make those calls.",
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
        "en": "Here's what's open on your record. I don't have repair times yet, because McKinley hasn't set target "
              "times for the assistant to share. If something has waited too long, I can send a note to the office.",
        "es": "Esto es lo que está abierto en su historial. Todavía no tengo horarios de reparación para "
              "compartir. Si algo lleva demasiado tiempo, puedo enviar una nota a la oficina.",
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
    "tour_ask_days": {
        "en": "Great. Which days work for you to visit?",
        "es": "Perfecto. ¿Qué días le funcionan para la visita?",
    },
    "tour_ask_time": {
        "en": "And what time of day is easiest: morning, afternoon or evening?",
        "es": "¿Y qué hora del día le conviene más: mañana, tarde o noche?",
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
              "look at it. I've written a note with the details so you won't have to start over.",
        "es": "Lo siento, es frustrante y no debería tener que insistir. Un miembro del equipo debe revisarlo. "
              "Escribí una nota con los detalles para que no tenga que empezar de nuevo.",
    },
    "other_language": {
        "en": "I can reply in English or Spanish. For other languages, a team member can help. I've prepared a "
              "note for the office.",
        "es": "Puedo responder en inglés o español. Para otros idiomas, un miembro del equipo puede ayudarle.",
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
        "en": "Okay, I haven't sent anything. Is there something else I can help with?",
        "es": "De acuerdo, no envié nada. ¿Le ayudo con algo más?",
    },
}

# Confirmation messages returned by the action endpoint after a prototype record was actually written (I-22,
# I-16 drafts). They state the real outcome and never promise timing.
CONFIRM: dict[str, dict[Lang, str]] = {
    "maintenance_request": {
        "en": "Request {id} is submitted for staff review. A team member reviews it before scheduling, and you "
              "can ask me for its status anytime.",
        "es": "La solicitud {id} se envió para revisión del personal. Un miembro del equipo la revisa antes de "
              "programarla; puede preguntarme por su estado cuando quiera.",
    },
    "tour_request": {
        "en": "Tour request {id} is sent to the leasing team. It isn't a confirmed booking: the team picks a time "
              "from your preferences and confirms it with you.",
        "es": "La solicitud de visita {id} se envió al equipo de arrendamiento. Todavía no es una cita confirmada: "
              "el equipo elige una hora según sus preferencias y se la confirma.",
    },
    "staff_handoff": {
        "en": "Your note {id} is in the office queue with the details, so you won't have to repeat yourself.",
        "es": "Su nota {id} está en la cola de la oficina con los detalles, para que no tenga que repetirlos.",
    },
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
    "resident_next": {"en": ["Report a repair", "Check my requests", "Talk to the office"],
                      "es": ["Reportar una reparación", "Ver mis solicitudes", "Hablar con la oficina"]},
}


def t(key: str, lang: Lang = "en", **kw: str) -> str:
    text = T[key].get(lang) or T[key]["en"]
    return text.format(**kw) if kw else text
