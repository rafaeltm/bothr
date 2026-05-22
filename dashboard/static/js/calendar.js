const weekdayNames = ['Dom', 'Lun', 'Mar', 'Mié', 'Jue', 'Vie', 'Sáb'];
const monthNames = ['Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio', 'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre'];

let currentDate = new Date();
let festivos = new Set();
let jornadaReducida = new Set();
let lastSelectedDate = null;

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

function isWeekendDateString(dateString) {
  const [year, month, day] = dateString.split('-').map(Number);
  const weekday = new Date(year, month - 1, day).getDay();
  return weekday === 0 || weekday === 6;
}

function sanitizeWorkdays(dateList) {
  return (dateList || []).filter((dateString) => !isWeekendDateString(dateString));
}

function toTimestamp(dateString) {
  const [year, month, day] = dateString.split('-').map(Number);
  return new Date(year, month - 1, day).getTime();
}

function getDateRange(startDateString, endDateString) {
  const [start, end] = [startDateString, endDateString].sort((a, b) => toTimestamp(a) - toTimestamp(b));
  const [startYear, startMonth, startDay] = start.split('-').map(Number);
  const cursor = new Date(startYear, startMonth - 1, startDay);
  const rangeEndTimestamp = toTimestamp(end);
  const range = [];
  while (cursor.getTime() <= rangeEndTimestamp) {
    range.push(formatDate(cursor));
    cursor.setDate(cursor.getDate() + 1);
  }
  return range;
}

function cycleDateState(dateString, renderAfterUpdate = true) {
  if (isWeekendDateString(dateString)) return;
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
  if (renderAfterUpdate) renderCalendar();
}

function updateMonthPicker() {
  const picker = document.getElementById('monthPicker');
  const year = currentDate.getFullYear();
  const month = String(currentDate.getMonth() + 1).padStart(2, '0');
  picker.value = `${year}-${month}`;
}

function handleDateSelection(dateString, useRangeSelection) {
  const dateStrings = useRangeSelection && lastSelectedDate ? getDateRange(lastSelectedDate, dateString) : [dateString];
  dateStrings.forEach((selectedDateString) => cycleDateState(selectedDateString, false));
  lastSelectedDate = dateString;
  renderCalendar();
}

function renderCalendar() {
  const grid = document.getElementById('calendarGrid');
  const title = document.getElementById('calendarTitle');
  grid.innerHTML = '';
  title.textContent = `${monthNames[currentDate.getMonth()]} ${currentDate.getFullYear()}`;
  updateMonthPicker();

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
    const isWeekend = cellDate.getDay() === 0 || cellDate.getDay() === 6;
    const state = getState(dateString);

    const cell = document.createElement('button');
    cell.type = 'button';
    cell.className = 'calendar-day';
    if (isWeekend) {
      cell.classList.add('is-weekend');
      cell.disabled = true;
    }
    if (state === 'festivo') cell.classList.add('is-festivo');
    if (state === 'jornada_reducida') cell.classList.add('is-reducida');
    cell.innerHTML = `
      <div class="fw-semibold">${day}</div>
      <div class="small mt-2">${
        isWeekend
          ? 'Bloqueado'
          : state === 'festivo'
            ? 'Festivo'
            : state === 'jornada_reducida'
              ? 'Jornada reducida'
              : 'Normal'
      }</div>
    `;
    if (!isWeekend) {
      cell.addEventListener('click', (event) => handleDateSelection(dateString, event.shiftKey));
    }
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
  festivos = new Set(sanitizeWorkdays(festivosData.festivos));
  jornadaReducida = new Set(sanitizeWorkdays(reducidaData.dias));
  renderCalendar();
}

async function saveCalendarData() {
  const festivosPayload = { festivos: sanitizeWorkdays(Array.from(festivos)).sort() };
  const reducidaPayload = { dias: sanitizeWorkdays(Array.from(jornadaReducida)).sort() };

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
      festivos = new Set(sanitizeWorkdays(data.festivos));
      jornadaReducida = new Set(sanitizeWorkdays(data.dias));
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

document.getElementById('monthPicker').addEventListener('change', (event) => {
  if (!event.target.value) return;
  const [year, month] = event.target.value.split('-').map(Number);
  currentDate = new Date(year, month - 1, 1);
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
