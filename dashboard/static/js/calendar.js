const weekdayNames = ['Dom', 'Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb'];
const monthNames = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'];

let currentDate = new Date();
let festivos = new Set();
let jornadaReducida = new Set();

function formatDate(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function getState(dateString) {
  if (festivos.has(dateString)) return 'festivo';
  if (jornadaReducida.has(dateString)) return 'jornada_reducida';
  return 'none';
}

function cycleDateState(dateString) {
  const state = getState(dateString);
  if (state === 'none') {
    festivos.add(dateString);
    jornadaReducida.delete(dateString);
  } else if (state === 'festivo') {
    festivos.delete(dateString);
    jornadaReducida.add(dateString);
  } else {
    festivos.delete(dateString);
    jornadaReducida.delete(dateString);
  }
  renderCalendar();
}

function renderCalendar() {
  const grid = document.getElementById('calendarGrid');
  const title = document.getElementById('calendarTitle');
  grid.innerHTML = '';
  title.textContent = `${monthNames[currentDate.getMonth()]} ${currentDate.getFullYear()}`;

  weekdayNames.forEach((name) => {
    const cell = document.createElement('div');
    cell.className = 'calendar-weekday';
    cell.textContent = name;
    grid.appendChild(cell);
  });

  const firstDay = new Date(currentDate.getFullYear(), currentDate.getMonth(), 1);
  const lastDay = new Date(currentDate.getFullYear(), currentDate.getMonth() + 1, 0);
  const startOffset = firstDay.getDay();

  for (let i = 0; i < startOffset; i += 1) {
    const emptyCell = document.createElement('div');
    emptyCell.className = 'calendar-day is-other-month';
    grid.appendChild(emptyCell);
  }

  for (let day = 1; day <= lastDay.getDate(); day += 1) {
    const cellDate = new Date(currentDate.getFullYear(), currentDate.getMonth(), day);
    const dateString = formatDate(cellDate);
    const state = getState(dateString);

    const cell = document.createElement('button');
    cell.type = 'button';
    cell.className = 'calendar-day';
    if (state === 'festivo') cell.classList.add('is-festivo');
    if (state === 'jornada_reducida') cell.classList.add('is-reducida');
    cell.innerHTML = `
      <div class="fw-semibold">${day}</div>
      <div class="small mt-2">${state === 'festivo' ? 'Festivo' : state === 'jornada_reducida' ? 'Jornada reducida' : 'Normal'}</div>
    `;
    cell.addEventListener('click', () => cycleDateState(dateString));
    grid.appendChild(cell);
  }
}

async function loadCalendarData() {
  const [festivosResponse, reducidaResponse] = await Promise.all([
    fetch('/api/festivos'),
    fetch('/api/jornada_reducida')
  ]);

  const festivosData = await festivosResponse.json();
  const reducidaData = await reducidaResponse.json();
  festivos = new Set(festivosData.festivos || []);
  jornadaReducida = new Set(reducidaData.dias || []);
  renderCalendar();
}

async function saveCalendarData() {
  const festivosPayload = { festivos: Array.from(festivos).sort() };
  const reducidaPayload = { dias: Array.from(jornadaReducida).sort() };

  const [festivosResponse, reducidaResponse] = await Promise.all([
    fetch('/api/festivos', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(festivosPayload)
    }),
    fetch('/api/jornada_reducida', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(reducidaPayload)
    })
  ]);

  if (!festivosResponse.ok) {
    throw new Error('No se pudieron guardar los festivos.');
  }
  if (!reducidaResponse.ok) {
    throw new Error('No se pudo guardar la jornada reducida.');
  }
}

function exportCalendarData() {
  const data = {
    festivos: Array.from(festivos).sort(),
    dias: Array.from(jornadaReducida).sort()
  };
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
  const link = document.createElement('a');
  link.href = URL.createObjectURL(blob);
  link.download = 'bothr-calendar.json';
  link.click();
  URL.revokeObjectURL(link.href);
}

function importCalendarData(file) {
  const reader = new FileReader();
  reader.onload = () => {
    try {
      const data = JSON.parse(reader.result);
      festivos = new Set(data.festivos || []);
      jornadaReducida = new Set(data.dias || []);
      renderCalendar();
      window.showToast('Calendario importado correctamente.');
    } catch (error) {
      window.showToast('El archivo JSON no es válido.', true);
    }
  };
  reader.readAsText(file);
}

document.getElementById('prevMonth').addEventListener('click', () => {
  currentDate = new Date(currentDate.getFullYear(), currentDate.getMonth() - 1, 1);
  renderCalendar();
});

document.getElementById('nextMonth').addEventListener('click', () => {
  currentDate = new Date(currentDate.getFullYear(), currentDate.getMonth() + 1, 1);
  renderCalendar();
});

document.getElementById('saveCalendar').addEventListener('click', async () => {
  try {
    await saveCalendarData();
    window.showToast('Calendario guardado correctamente.');
  } catch (error) {
    window.showToast(error.message, true);
  }
});

document.getElementById('exportBtn').addEventListener('click', exportCalendarData);
document.getElementById('importBtn').addEventListener('click', () => document.getElementById('importFile').click());
document.getElementById('importFile').addEventListener('change', (event) => {
  const [file] = event.target.files;
  if (file) {
    importCalendarData(file);
  }
  event.target.value = '';
});

loadCalendarData().catch(() => window.showToast('No se pudo cargar el calendario.', true));
